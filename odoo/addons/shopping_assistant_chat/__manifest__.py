{
    "name": "Shopping Assistant Chat",
    "summary": "Phone spec fields, chatbot order entry point and a floating chat window on the website",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "license": "LGPL-3",
    "author": "duyle215",
    "depends": ["sale_stock", "crm", "website_sale"],
    "data": [
        "data/config_parameter.xml",
        "views/product_template_views.xml",
        "views/crm_lead_views.xml",
        "views/sale_order_views.xml",
        "views/website_chat_templates.xml",
    ],
    "installable": True,
    "application": False,
}
