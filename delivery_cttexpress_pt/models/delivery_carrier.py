# Copyright 2024 Open Source Integrators - Daniel Reis
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .cttexpress_master_data import (
    CTTEXPRESS_DELIVERY_STATES_STATIC,
    CTTEXPRESS_SERVICES,
)
from .cttexpress_request import CTTExpressRequest


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("cttexpresspt", "CTT Express Portugal")],
        ondelete={"cttexpresspt": "set default"},
    )

    ##ctt_express_api_url = fields.Char(string="API URL", copy=False)
    ##ctt_express_authentication_id = fields.Char(string="Authentication ID",copy=False)
    ##ctt_express_client_id = fields.Char(string="Client ID",copy=False)
    ##ctt_express_contract_id = fields.Char(string="Contract ID",copy=False)
    ##ctt_express_distribution_channel_id = fields.Char(string="Distribution Channel ID",copy=False)
    ##ctt_express_user_id = fields.Char(string="user ID",copy=False)

    cttexpress_user = fields.Char(string="User")
    cttexpress_password = fields.Char(string="Password")
    cttexpress_customer = fields.Char(string="Customer code")
    cttexpress_agency = fields.Char(string="Agency code")
    cttexpress_contract = fields.Char(string="Contract code")


    ##ctt_express_provider_package_id = fields.Many2one('stock.package.type', string="Package Info",
    ##                                                  help="Default Package")
    ##ctt_express_sub_product = fields.Selection(
    ##    [('ENCF005.01', '19'), ('EMSF010.01', '19 Múltiplo'), ('EMSF028.01', '13 Múltiplo')], string="ProductID")
    ##ctt_express_label_type = fields.Selection([('zpl', 'ZPL'), ('pdf', 'PDF')], string="Label Type")
    ##has_sender_information = fields.Boolean(string="Sender Information On Label ?", copy=False)
    ##export_type = fields.Selection([('Permanent', 'Permanent'),
    ##                                ('TemporaryPassiveImprovement', 'Temporary (Passive Improvement)'),
    ##                                ('TemporaryExhibition', 'Temporary (Exhibition)')], string="Export Type")
    ##upc_code_value = fields.Selection([('Samples', 'Samples'),
    ##                                   ('Documents', 'Documents'),
    ##                                   ('Goods', 'Goods'),
    ##                                   ('Others', 'Others'),
    ##                                   ('Devolution', 'Devolution')], string="UPC Code")

    cttexpresspt_shipping_type = fields.Selection(
        selection=CTTEXPRESS_SERVICES,
        string="Shipping type",
    )
    cttexpress_document_model_code = fields.Selection(
        selection=[
            ("SINGLE", "Single"),
            ("MULTI1", "Multi 1"),
            ("MULTI3", "Multi 3"),
            ("MULTI4", "Multi 4"),
        ],
        default="SINGLE",
        string="Document model",
    )
    cttexpress_document_format = fields.Selection(
        selection=[("PDF", "PDF"), ("PNG", "PNG"), ("BMP", "BMP")],
        default="PDF",
        string="Document format",
    )
    cttexpress_document_offset = fields.Integer(string="Document Offset")

    @api.onchange("delivery_type")
    def _onchange_delivery_type_ctt(self):
        """Default price method for CTT as the API can't gather prices."""
        if self.delivery_type == "cttexpresspt":
            self.price_method = "base_on_rule"

    def _cttexpresspr_request(self):
        """Get CTT Request object

        :return CTTExpressRequest: CTT Express Request object
        """
        return CTTExpressRequest(
            user=self.cttexpress_user,
            password=self.cttexpress_password,
            agency=self.cttexpress_agency,
            customer=self.cttexpress_customer,
            contract=self.cttexpress_contract,
            prod=self.prod_environment,
        )

    @api.model
    def _ctt_log_request(self, ctt_request):
        """When debug is active requests/responses will be logged in ir.logging

        :param ctt_request ctt_request: CTT Express request object
        """
        self.log_xml(ctt_request.ctt_last_request, "ctt_request")
        self.log_xml(ctt_request.ctt_last_response, "ctt_response")

    def _ctt_check_error(self, error):
        """Common error checking. We stop the program when an error is returned.

        :param list error: List of tuples in the form of (code, description)
        :raises UserError: Prompt the error to the user
        """
        if not error:
            return
        error_msg = ""
        for code, msg in error:
            if not code:
                continue
            error_msg += "{} - {}\n".format(code, msg)
        if not error_msg:
            return
        raise UserError(_("CTT Express Error:\n\n%s") % error_msg)

    @api.model
    def _cttexpress_format_tracking(self, tracking):
        """Helper to forma tracking history strings

        :param OrderedDict tracking: CTT tracking values
        :return str: Tracking line
        """
        status = "{} - [{}] {}".format(
            fields.Datetime.to_string(tracking["StatusDateTime"]),
            tracking["StatusCode"],
            tracking["StatusDescription"],
        )
        if tracking["IncidentCode"]:
            status += " ({}) - {}".format(
                tracking["IncidentCode"], tracking["IncidentDescription"]
            )
        return status

    @api.onchange("cttexpress_shipping_type")
    def _onchange_cttexpress_shipping_type(self):
        """Control service validity according to credentials

        :raises UserError: We list the available services for given credentials
        """
        if not self.cttexpress_shipping_type:
            return
        # Avoid checking if credentianls aren't setup or are invalid
        try:
            self.action_ctt_validate_user()
        except UserError:
            return
        ctt_request = self._ctt_request()
        error, service_types = ctt_request.get_service_types()
        self._ctt_log_request(ctt_request)
        self._ctt_check_error(error)
        type_codes, type_descriptions = zip(*service_types)
        if self.cttexpress_shipping_type not in type_codes:
            service_name = dict(
                self._fields["cttexpress_shipping_type"]._description_selection(
                    self.env
                )
            )[self.cttexpress_shipping_type]
            raise UserError(
                _(
                    "This CTT Express service (%(service_name)s) isn't allowed for "
                    "this account configuration. Please choose one of the followings\n"
                    "%(type_descriptions)s",
                    service_name=service_name,
                    type_descriptions=type_descriptions,
                )
            )

    def action_ctt_validate_user(self):
        """Maps to API's ValidateUser method

        :raises UserError: If the user credentials aren't valid
        """
        self.ensure_one()
        ctt_request = self._ctt_request()
        error = ctt_request.validate_user()
        self._ctt_log_request(ctt_request)
        # For user validation success there's an error return as well.
        # We better ignore it.
        if error[0]:
            self._ctt_check_error(error)

    def _prepare_cttexpress_shipping(self, picking):
        """Convert picking values for CTT Express API

        :param record picking: `stock.picking` record
        :return dict: Values prepared for the CTT connector
        """
        self.ensure_one()
        # A picking can be delivered from any warehouse
        sender_partner = (
            picking.picking_type_id.warehouse_id.partner_id
            or picking.company_id.partner_id
        )
        recipient = picking.partner_id
        recipient_entity = picking.partner_id.commercial_partner_id
        weight = picking.shipping_weight
        reference = picking.name
        if picking.sale_id:
            reference = "{}-{}".format(picking.sale_id.name, reference)
        return {
            "ClientReference": reference,  # Optional
            "ClientDepartmentCode": None,  # Optional (no core field matches)
            "ItemsCount": picking.number_of_packages,
            "IsClientPodScanRequired": None,  # Optional
            "RecipientAddress": recipient.street,
            "RecipientCountry": recipient.country_id.code,
            "RecipientEmail": recipient.email or recipient_entity.email,  # Optional
            "RecipientSMS": None,  # Optional
            "RecipientMobile": recipient.mobile or recipient_entity.mobile,  # Optional
            "RecipientName": recipient.name or recipient_entity.name,
            "RecipientPhone": recipient.phone or recipient_entity.phone,
            "RecipientPostalCode": recipient.zip,
            "RecipientTown": recipient.city,
            "RefundValue": None,  # Optional
            "HasReturn": None,  # Optional
            "IsSaturdayDelivery": None,  # Optional
            "SenderAddress": sender_partner.street,
            "SenderName": sender_partner.name,
            "SenderPhone": sender_partner.phone or "",
            "SenderPostalCode": sender_partner.zip,
            "SenderTown": sender_partner.city,
            "ShippingComments": None,  # Optional
            "ShippingTypeCode": self.cttexpress_shipping_type,
            "Weight": int(weight * 1000) or 1,  # Weight in grams
            "PodScanInstructions": None,  # Optional
            "IsFragile": None,  # Optional
            "RefundTypeCode": None,  # Optional
            "CreatedProcessCode": "ODOO",  # Optional
            "HasControl": None,  # Optional
            "HasFinalManagement": None,  # Optional
        }

    def cttexpresspt_send_shipping(self, pickings):
        """
        Method called when a picking is confirmed
        Returns a dict with tracking number and delivery price zero

        """

        ctt_request = self._ctt_request()
        result = []
        for picking in pickings:
            vals = self._prepare_cttexpress_shipping(picking)
            try:
                error, documents, tracking = ctt_request.manifest_shipping(vals)
                self._ctt_check_error(error)
            except Exception as e:
                raise (e)
            finally:
                self._ctt_log_request(ctt_request)
            vals.update({"tracking_number": tracking, "exact_price": 0})
            # The default shipping method doesn't allow to configure the label
            # format, so once we get the tracking, we ask for it again.
            documents = self.cttexpress_get_label(tracking)
            # We post an extra message in the chatter with the barcode and the
            # label because there's clean way to override the one sent by core.
            body = _("CTT Shipping Documents")
            picking.message_post(body=body, attachments=documents)
            result.append(vals)
        return result

    def XXXcttexpress_get_label(self, reference):
        """Generate label for picking

        :param str reference: shipping reference
        :returns tuple: (file_content, file_name)
        """
        self.ensure_one()
        if not reference:
            return False
        ctt_request = self._ctt_request()
        try:
            error, label = ctt_request.get_documents_multi(
                reference,
                model_code=self.cttexpress_document_model_code,
                kind_code=self.cttexpress_document_format,
                offset=self.cttexpress_document_offset,
            )
            self._ctt_check_error(error)
        except Exception as e:
            raise (e)
        finally:
            self._ctt_log_request(ctt_request)
        if not label:
            return False
        return label

    # def cttexpresspt_tracking_state_update(self, picking):
    # Not provided

    def cttexpresspt_cancel_shipment(self, pickings):
        """Cancel the expedition"""
        raise ValidationError(_("Not provided by the CTT Express API"))

    def cttexpresspt_get_tracking_link(self, picking):
        """Get CTT Express tracking link"""
        tracking_url = (
            "https://www.ctt.pt/feapl_2/app/"
            "open/objectSearch/objectSearch.jspx?request_locale=en"
        )
        return tracking_url.format(picking.carrier_tracking_ref)
