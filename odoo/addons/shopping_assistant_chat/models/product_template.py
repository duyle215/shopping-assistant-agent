from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_phone = fields.Boolean("Phone", index=True)
    phone_brand = fields.Char("Brand", index=True)
    phone_model = fields.Char("Model")
    phone_chipset = fields.Char("Chipset")
    phone_ram_gb = fields.Integer("RAM (GB)")
    phone_storage_gb = fields.Char(
        "Storage options (GB)", help="Comma-separated, e.g. 128,256,512"
    )
    phone_max_storage_gb = fields.Integer(
        "Max storage (GB)", compute="_compute_phone_max_storage_gb", store=True
    )
    phone_screen_inch = fields.Float("Screen (inch)", digits=(4, 2))
    phone_refresh_rate_hz = fields.Integer("Refresh rate (Hz)")
    phone_battery_mah = fields.Integer("Battery (mAh)")
    phone_charging_w = fields.Integer("Charging (W)")
    phone_main_camera_mp = fields.Integer("Main camera (MP)")
    phone_weight_g = fields.Integer("Weight (g)")
    phone_os = fields.Selection([("iOS", "iOS"), ("Android", "Android")], "OS", index=True)
    phone_release_year = fields.Integer("Release year")
    # Units that can still be sold now: on hand minus units reserved by confirmed orders
    chat_free_qty = fields.Integer("Free to sell", compute="_compute_chat_free_qty")

    def _compute_chat_free_qty(self):
        for tmpl in self:
            tmpl.chat_free_qty = int(sum(tmpl.product_variant_ids.mapped("free_qty")))

    @api.depends("phone_storage_gb")
    def _compute_phone_max_storage_gb(self):
        for tmpl in self:
            tmpl.phone_max_storage_gb = max(tmpl._phone_storage_list() or [0])

    def _phone_storage_list(self):
        self.ensure_one()
        return [int(s) for s in (self.phone_storage_gb or "").split(",") if s.strip().isdigit()]
