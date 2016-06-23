#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from .invoice import *
from .shipment import *
from .party import *
from .company import *
from .user import *
from .tax import *
from .product import *
from .withholding import *
from .account import *
def register():
    Pool.register(
        Party,
        Invoice,
        SendSriLoteStart,
        ShipmentOut,
        SendSriLoteStartShipment,
        Company,
        User,
        TaxElectronic,
        TaxSpecial,
        Tax,
        Category,
        Template,
        AccountWithholding,
        Configuration,
        module='nodux_account_electronic_invoice_ec', type_='model')
    Pool.register(
        SendSriLote,
        SendSriLoteShipment,
        module='nodux_account_electronic_invoice_ec', type_='wizard')
    Pool.register(
        InvoiceReport,
        PrintWithholdingE,
        PrintShipmentE,
        module='nodux_account_electronic_invoice_ec', type_='report')
