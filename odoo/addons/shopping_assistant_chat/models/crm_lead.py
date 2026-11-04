from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    chat_session_id = fields.Char("Chat session", index=True, copy=False)
