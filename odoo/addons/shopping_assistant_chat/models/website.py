from odoo import models

URL_PARAM = "shopping_assistant_chat.app_url"


class Website(models.Model):
    _inherit = "website"

    def chat_assistant_url(self, lang_code=None):
        """URL of the chatbot embed page, or "" when not configured (widget hidden)."""
        base = (self.env["ir.config_parameter"].sudo().get_param(URL_PARAM) or "").rstrip("/")
        if not base:
            return ""
        lang = "vi" if (lang_code or "").startswith("vi") else "en"
        return f"{base}/embed?lang={lang}"
