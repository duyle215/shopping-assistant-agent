import re

from odoo import api, fields, models
from odoo.exceptions import UserError

CHAT_ORIGIN = "Chatbot"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    chat_session_id = fields.Char("Chat session", index=True, copy=False)
    chat_shortage = fields.Integer(
        "Missing units", copy=False, help="Units short when the chatbot took the order"
    )

    @api.model
    def _chat_find_or_create_partner(self, name, phone):
        phone = re.sub(r"[\s.\-]", "", phone or "")
        partner = self.env["res.partner"].search([("phone", "=", phone)], limit=1)
        if not partner:
            partner = self.env["res.partner"].create({"name": name.strip(), "phone": phone})
        return partner

    @api.model
    def chat_place_order(self, product_tmpl_id, quantity, customer_name, customer_phone, session_id=None):
        """Order entry point for the chatbot, in one database transaction.

        Enough free stock: the order is confirmed (stock is reserved on the delivery).
        Not enough: the order stays a quotation with ``chat_shortage`` set, for staff to follow up.
        """
        if quantity <= 0:
            raise UserError("Quantity must be positive.")
        if not (customer_name or "").strip() or not (customer_phone or "").strip():
            raise UserError("Customer name and phone are required.")
        tmpl = self.env["product.template"].browse(int(product_tmpl_id)).exists()
        if not tmpl or not tmpl.sale_ok or not tmpl.is_phone:
            return {"error": "product_not_found", "product_id": product_tmpl_id}

        # Writing the product row serialises chatbot orders for the same product. Odoo runs
        # in REPEATABLE READ, so a concurrent order fails with a serialisation error and the
        # request is retried on a fresh snapshot: it never reads stock another order just took.
        self.env.cr.execute(
            "UPDATE product_template SET write_date = now() WHERE id = %s", [tmpl.id]
        )
        product = tmpl.product_variant_id
        free_before = int(product.free_qty)

        partner = self._chat_find_or_create_partner(customer_name, customer_phone)
        order = self.create(
            {
                "partner_id": partner.id,
                "origin": CHAT_ORIGIN,
                "chat_session_id": session_id,
                "order_line": [
                    fields.Command.create({"product_id": product.id, "product_uom_qty": quantity})
                ],
            }
        )
        result = {
            "order_id": order.id,
            "order_ref": order.name,
            "product_id": tmpl.id,
            "product_name": tmpl.name,
            "quantity": quantity,
            "unit_price": order.order_line[:1].price_unit,
            "amount_total": order.amount_total,
            "currency": order.currency_id.name,
            "free_qty_before": free_before,
        }
        if free_before >= quantity:
            order.action_confirm()
            product.invalidate_recordset(["free_qty"])
            result.update(status="confirmed", remaining_stock=int(product.free_qty))
        else:
            order.chat_shortage = quantity - free_before
            order.message_post(
                body=f"Chatbot order: {quantity} requested, {free_before} in stock. "
                "Waiting for restock before confirming."
            )
            result.update(status="pending_restock", shortage=quantity - free_before)
        return result

    @api.model
    def chat_update_customer(self, session_id, customer_name, customer_phone):
        """Attach name and phone to the latest quotation the chatbot left in this session."""
        order = self.search(
            [("chat_session_id", "=", session_id), ("state", "=", "draft")], order="id desc", limit=1
        )
        if not order:
            return {"status": "no_pending_order"}
        partner = self._chat_find_or_create_partner(customer_name, customer_phone)
        order.partner_id = partner
        return {"status": "updated", "order_ref": order.name}
