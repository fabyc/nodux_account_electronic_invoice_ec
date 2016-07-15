# -*- coding: utf-8 -*-

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
from trytond.rpc import RPC
import datetime
import psycopg2
import collections
import logging
from decimal import Decimal
from OpenSSL.crypto import *
import base64
import StringIO
from trytond.pyson import Eval
from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool, PoolMeta
from lxml import etree
from lxml.etree import DocumentInvalid
from xml.dom.minidom import parse, parseString
from socket import error as SocketError
import xml.etree.cElementTree as ET
import time
import code128
import xml.etree.ElementTree
import smtplib, os
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEBase import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders
from email.Utils import COMMASPACE, formatdate
from email import Encoders
import xmlrpclib
import shutil
import os.path
import unicodedata
import re

__all__ = ['Invoice', 'SendSriLoteStart', 'SendSriLote','InvoiceReport']
__metaclass__ = PoolMeta

tipoDocumento = {
    'out_invoice': '01',
    'out_credit_note': '04',
    'out_debit_note': '05',
    'out_shipment': '06',
    'in_withholding': '07',
}

tipoIdentificacion = {
    '04' : '04',
    '05' : '05',
    '06' : '06',
    '07' : '07',
}
#No Objeto deImpuesto 6, Exento de IVA 7

tarifaImpuesto = {
    1: '2',
    2: '2',
    3: '0',
    4: '0',
    5: '0',
    6: '0'
}

tipoIdentificacion2 = {
    '04' : '01',
    '05' : '02',
    '06' : '03',
}

identificacionCliente = {
    '04': '04',
    '05': '05',
    '06': '06',
    '07': '06',
    }

tpIdCliente = {
    'ruc': '04',
    'cedula': '05',
    'pasaporte': '06',
    }

tipoProvedor = {
    'persona_natural' : '01',
    'sociedad': '02',
}

_CREDIT_TYPE = {
    None: None,
    'out_invoice': 'out_credit_note',
    'in_invoice': 'in_credit_note',
    'out_credit_note': 'out_invoice',
    'in_credit_note': 'in_invoice',
    }

# estructura para conexion con xmlrpc (cuando se envia directo el user y pass no se pone '')
#s = xmlrpclib.ServerProxy ('http://%s:%s@192.168.1.45:9069/prueba_auth' % (USER, PASSWORD))
class Invoice():

    __name__ = 'account.invoice'

    lote = fields.Boolean(u'Envío de Facturas por Lote', states={
            'readonly' : Eval('state') != 'draft',
            })
    #ambiente = fields.Date(u'Fecha de Factura que se modifica')
    estado_sri = fields.Char('Estado Facturacion-Electronica', size=24, readonly=True, states={
            'invisible': Eval('type') == 'in_invoice',
            })
    mensaje = fields.Text('Mensaje de error SRI', readonly=True, states={
            'invisible': Eval('estado_sri') != 'NO AUTORIZADO',
            })
    path_xml = fields.Char(u'Path archivo xml de comprobante', readonly=True)
    path_pdf = fields.Char(u'Path archivo pdf de factura', readonly=True)
    numero_autorizacion = fields.Char(u'Número de Autorización')
    fisic_invoice = fields.Boolean('Fisic Invoice', states={
            'readonly' : Eval('state')!= 'draft',
            'invisible' : Eval('type') != 'out_invoice',
            })

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._check_modify_exclude = ['estado_sri', 'path_xml', 'numero_autorizacion', 'ambiente','mensaje','path_pdf', 'state', 'payment_lines', 'cancel_move',
                'invoice_report_cache', 'invoice_report_format', 'move']
        cls._transitions |= set((('posted', 'draft'),))

    def _credit(self):
        '''
        Return values to credit invoice.
        '''
        res = {}
        res['type'] = _CREDIT_TYPE[self.type]
        res['number_w'] = self.number
        res['ambiente'] = self.invoice_date

        for field in ('description', 'comment'):
            res[field] = getattr(self, field)

        for field in ('company', 'party', 'invoice_address', 'currency',
                'journal', 'account', 'payment_term'):
            res[field] = getattr(self, field).id

        res['lines'] = []
        if self.lines:
            res['lines'].append(('create',
                    [line._credit() for line in self.lines]))

        res['taxes'] = []
        to_create = [tax._credit() for tax in self.taxes if tax.manual]
        if to_create:
            res['taxes'].append(('create', to_create))
        return res

    @staticmethod
    def default_lote():
        return True

    @classmethod
    def count_invoice(cls, party, start_p_start, end_p_start, start_p_end, end_p_end):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoice = Invoice.search([('type','=', 'out_invoice'),('state','in', ('posted','paid')),('company.party.vat_number', '=', party)])
        credit = Invoice.search([('type','=', 'out_credit_note'),('state','in', ('posted','paid')),('company.party.vat_number', '=', party)])
        withholding = Invoice.search([('type','=', 'in_withholding'),('state','in', ('posted','paid')),('company.party.vat_number', '=', party)])
        debit = Invoice.search([('type','=', 'out_debit_note'),('state','in', ('posted','paid')),('company.party.vat_number', '=', party)])
        number_invoice = 0
        number_credit = 0
        number_debit = 0
        number_withholding = 0
        number_shipment = 0

        if Invoice:
            for i in invoice:
                if i.invoice_date >= start_p_start and i.invoice_date<=end_p_start:
                    number_invoice = number_invoice +1
            for c in credit:
                number_credit = number_credit +1
            for w in withholding:
                number_withholding = number_withholding +1
            for d in debit:
                number_debit = number_debit +1
            """
            for s in shipment:
                number_shipment = number_shipment +1
            """
        total_voucher= number_invoice + number_credit +number_withholding+number_debit + number_shipment

        return (number_invoice, number_credit, number_debit, number_withholding, number_shipment)


    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, invoices):
        print "Metodo normal de facturacion electronica"
        Move = Pool().get('account.move')
        moves = []

        for invoice in invoices:
            invoice.limit()
            if invoice.type == u'out_invoice' or invoice.type == u'out_credit_note':
                invoice.create_move()
                moves.append(invoice.create_move())
                if invoice.fisic_invoice == True:
                    pass
                else:
                    invoice.set_number()
                    if invoice.lote == False:
                        invoice.get_invoice_element()
                        invoice.get_tax_element()
                        invoice.generate_xml_invoice()
                        invoice.get_detail_element()
                        invoice.action_generate_invoice()
                        invoice.connect_db()
            elif invoice.type == 'in_invoice':
                pool = Pool()
                Module = pool.get('ir.module.module')
                module = Module.search([('name', '=', 'nodux_account_withholding_in_ec'), ('state', '=', 'installed')])
                invoice.create_move()
                if invoice.number:
                    pass
                else:
                    invoice.set_number()
                moves.append(invoice.create_move())
                if module:
                    Configuration = pool.get('account.configuration')
                    w = False
                    if Configuration(1).lote != None:
                        w = Configuration(1).lote

                    if w == False:
                        Withholding = Pool().get('account.withholding')
                        withholdings = Withholding.search([('number'), '=', invoice.ref_withholding])
                        for withholding in withholdings:
                        #invoice.authenticate()
                            if withholding.fisic == True:
                                pass
                            else:
                                withholding.get_invoice_element_w()
                                withholding.get_tax_element()
                                withholding.generate_xml_invoice_w()
                                withholding.get_taxes()
                                withholding.action_generate_invoice_w()
                                withholding.connect_db()

            elif invoice.type == 'out_debit_note':
                invoice.create_move()
                invoice.set_number()
                moves.append(invoice.create_move())
                """
                if invoice.lote==False:
                    #invoice.authenticate()
                    invoice.get_tax_element()
                    invoice.get_debit_note_element()
                    invoice.get_detail_debit_note()
                    invoice.generate_xml_debit_note()
                    invoice.action_generate_debit_note()
                    invoice.connect_db()
                 """
        cls.write([i for i in invoices if i.state != 'posted'], {
                'state': 'posted',
                })
        Move.post([m for m in moves if m.state != 'posted'])

    def web_service(self):
        CONEXION = 'UD NO HA CONFIGURADO LOS DATOS DE CONEXION CON EL WS, \nCOMUNIQUESE CON EL ADMINISTRADOR DEL SISTEMA'
        pool = Pool()
        conexions = pool.get('res.user')
        conexion = conexions.search([('id', '=', 1)])
        if conexion:
            for c in conexion:
                if c.direccion:
                    address = c.cabecera+"://"+base64.decodestring(c.usuario)+":"+base64.decodestring(c.pass_db)+"@"+c.direccion+":"+c.puerto+"/"+base64.decodestring(c.name_db)
                    return address
                else:
                    self.raise_user_error(CONEXION)


    def connect_db(self):

        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        pool = Pool()
        nombre = self.party.name
        cedula = self.party.vat_number
        ruc = self.company.party.vat_number
        nombre_e = self.company.party.name
        tipo = self.type
        fecha = str(self.invoice_date)
        empresa = self.company.party.name
        numero = self.number
        path_xml = self.path_xml
        path_pdf = self.path_pdf
        estado = self.estado_sri
        auth = self.numero_autorizacion
        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        for c in correo:
            if c.party == self.party:
                to_email = c.value
            if c.party == self.company.party:
                to_email_2 = c.value
        email_e= to_email_2
        email = to_email
        total = str(self.total_amount)
        s.model.nodux_electronic_invoice_auth.conexiones.connect_db( nombre, cedula, ruc, nombre_e, tipo, fecha, empresa, numero, path_xml, path_pdf,estado, auth, email, email_e, total, {})

    def get_ventas(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        invoices_paid= Invoice.search([('type','=','out_invoice'), ('state','=', 'paid')])
        invoices_posted = Invoice.search([('state','=', 'posted'), ('type','=','out_invoice')])
        lines = MoveLine.search([('state', '=', 'valid')])
        total_ventas_paid = 0
        total_ventas_posted = 0

        for i in invoices_paid:
            for l in lines:
                if i.move == l.move:
                    total_ventas_paid = total_ventas_paid + l.debit

        for i2 in invoices_posted:
            for l2 in lines:
                if i2.move == l2.move:
                    total_ventas_posted = total_ventas_posted + l2.debit
        total_ventas = total_ventas_paid + total_ventas_posted

        return total_ventas


    def limit(self):
        LIMIT_EXCEEDED= u"Ha alcanzado el número máximo de emision de facturas. \nComuníquese con nosotros, para contratar el servicio"
        pool = Pool()
        total_paid = 0
        total_posted = 0
        Invoice = pool.get('account.invoice')
        invoices_paid= Invoice.search([('state','=', 'paid'), ('company', '=', self.company)])
        invoices_posted = Invoice.search([('state','=', 'posted'), ('company', '=', self.company)])


        for i in invoices_paid:
            total_paid = total_paid + 1

        for i2 in invoices_posted:
            total_posted = total_posted + 1

        total_ventas = total_paid + total_posted

        if total_ventas > 1000:
            self.raise_user_error(LIMIT_EXCEEDED)
        return total_ventas

    def replace_charter(self, cadena):
        reemplazo = {u"Â":"A", u"Á":"A", u"À":"A", u"Ä":"A", u"É":"E", u"È":"E", u"Ê":"E",u"Ë":"E",
            u"Í":"I",u"Ì":"I",u"Î":"I",u"Ï":"I",u"Ó":"O",u"Ò":"O",u"Ö":"O",u"Ô":"O",u"Ú":"U",u"Ù":"U",u"Ü":"U",
            u"Û":"U",u"á":"a",u"à":"a",u"â":"a",u"ä":"a",u"é":"e",u"è":"e",u"ê":"e",u"ë":"e",u"í":"i",u"ì":"i",
            u"ï":"i",u"î":"i",u"ó":"o",u"ò":"o",u"ô":"o",u"ö":"o",u"ú":"u",u"ù":"u",u"ü":"u",u"û":"u",u"ñ":"n",
            u"Ñ":"N"}
        regex = re.compile("(%s)" % "|".join(map(re.escape, reemplazo.keys())))
        nueva_cadena = regex.sub(lambda x: str(reemplazo[x.string[x.start():x.end()]]), cadena)
        return nueva_cadena

    def get_tax_element(self):
        company = self.company
        number = self.number
        #auth = self.journal_id.auth_id
        infoTributaria = etree.Element('infoTributaria')
        etree.SubElement(infoTributaria, 'ambiente').text = self.company.tipo_de_ambiente
        #proxy.SriService.get_active_env()
        etree.SubElement(infoTributaria, 'tipoEmision').text = self.company.emission_code
        etree.SubElement(infoTributaria, 'razonSocial').text = self.replace_charter(self.company.party.name)
        if self.company.party.commercial_name:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.commercial_name
        etree.SubElement(infoTributaria, 'ruc').text = self.company.party.vat_number
        etree.SubElement(infoTributaria, 'claveAcceso').text = self.generate_access_key()
        etree.SubElement(infoTributaria, 'codDoc').text = tipoDocumento[self.type]
        etree.SubElement(infoTributaria, 'estab').text = number[0:3]
        etree.SubElement(infoTributaria, 'ptoEmi').text = number[4:7]
        etree.SubElement(infoTributaria, 'secuencial').text = number[8:17]
        if self.company.party.addresses:
            etree.SubElement(infoTributaria, 'dirMatriz').text = self.company.party.addresses[0].street
        return infoTributaria

    def get_invoice_element(self):
        company = self.company
        party = self.party
        infoFactura = etree.Element('infoFactura')
        etree.SubElement(infoFactura, 'fechaEmision').text = self.invoice_date.strftime('%d/%m/%Y')
        if self.company.party.addresses:
            etree.SubElement(infoFactura, 'dirEstablecimiento').text = self.company.party.addresses[0].street
        if self.company.party.contribuyente_especial_nro:
            etree.SubElement(infoFactura, 'contribuyenteEspecial').text = self.company.party.contribuyente_especial_nro
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoFactura, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoFactura, 'obligadoContabilidad').text = 'NO'
        if self.party.type_document:
            etree.SubElement(infoFactura, 'tipoIdentificacionComprador').text = tipoIdentificacion[self.party.type_document]
        else:
            self.raise_user_error("No ha configurado el tipo de identificacion del cliente")
        etree.SubElement(infoFactura, 'razonSocialComprador').text = self.replace_charter(self.party.name)
        etree.SubElement(infoFactura, 'identificacionComprador').text = self.party.vat_number
        etree.SubElement(infoFactura, 'totalSinImpuestos').text = '%.2f' % (self.untaxed_amount)
        etree.SubElement(infoFactura, 'totalDescuento').text = '0.00' #descuento esta incluido en el precio poner 0.0 por defecto

        #totalConImpuestos
        totalConImpuestos = etree.Element('totalConImpuestos')

        for tax in self.taxes:
            #if tax.tax_group in ['vat', 'vat0', 'ice', 'other']:
            totalImpuesto = etree.Element('totalImpuesto')
            #de acuerdo a niif

            if str('{:.0f}'.format(tax.tax.rate*100)) == '12':
                codigoPorcentaje = '2'
                codigo = '2'
            if str('{:.0f}'.format(tax.tax.rate*100)) == '0':
                codigoPorcentaje = '0'
                codigo = '2'
            if str('{:.0f}'.format(tax.tax.rate*100)) == '14':
                codigoPorcentaje = '3'
                codigo = '2'
            if tax.tax.rate == None:
                codigoPorcentaje = '6'
            etree.SubElement(totalImpuesto, 'codigo').text = codigo
            etree.SubElement(totalImpuesto, 'codigoPorcentaje').text = codigoPorcentaje
            etree.SubElement(totalImpuesto, 'baseImponible').text = '{:.2f}'.format(tax.base)
            etree.SubElement(totalImpuesto, 'valor').text = '{:.2f}'.format(tax.amount)
            totalConImpuestos.append(totalImpuesto)

        infoFactura.append(totalConImpuestos)
        etree.SubElement(infoFactura, 'propina').text = '0.00'
        etree.SubElement(infoFactura, 'importeTotal').text = '{:.2f}'.format(self.total_amount)
        etree.SubElement(infoFactura, 'moneda').text = 'DOLAR'

        return infoFactura

    def get_detail_element(self):
        def fix_chars(code):
            if code:
                #reemplazar caracteres http://www.genbetadev.com/python/reemplazo-multiple-de-cadenas-en-python
                code.replace(u'%',' ').replace(u'º', ' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                code = ''.join((c for c in unicodedata.normalize('NFD', code) if unicodedata.category(c) != 'Mn'))
                return code
            return '1'

        detalles = etree.Element('detalles')

        for line in self.lines:
            pool = Pool()
            Taxes1 = pool.get('product.category-customer-account.tax')
            Taxes2 = pool.get('product.template-customer-account.tax')

            detalle = etree.Element('detalle')
            etree.SubElement(detalle, 'codigoPrincipal').text = fix_chars(line.product.code)
            etree.SubElement(detalle, 'descripcion').text = self.replace_charter(line.description)#fix_chars(line.description)
            etree.SubElement(detalle, 'cantidad').text = '%.2f' % (line.quantity)
            etree.SubElement(detalle, 'precioUnitario').text = '%.2f' % (line.unit_price)
            etree.SubElement(detalle, 'descuento').text = '0.00'
            etree.SubElement(detalle, 'precioTotalSinImpuesto').text = '%.2f' % (line.amount)
            impuestos = etree.Element('impuestos')
            impuesto = etree.Element('impuesto')
            etree.SubElement(impuesto, 'codigo').text = "2"

            if line.product.iva_category == True:
                codigoPorcentaje_e_o = line.product.category.iva_tarifa
            else:
                codigoPorcentaje_e_o = line.product.iva_tarifa

            if line.product.taxes_category == True:
                if line.product.category.taxes_parent == True:
                    taxes1= Taxes1.search([('category','=', line.product.category.parent)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                else:
                    taxes1= Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
            else:
                taxes1= Taxes1.search([('category','=', line.product.category)])
                taxes2 = Taxes2.search([('product','=', line.product)])
                taxes3 = Taxes2.search([('product','=', line.product.template)])

            if taxes1:
                for t in taxes1:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                    if t.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            elif taxes2:
                for t in taxes2:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                        codigo = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                        codigo = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                        codigo = '2'
                    if t.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            elif taxes3:
                for t in taxes3:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                        codigo = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                        codigo = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                        codigo = '2'
                    if t.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            detalle.append(impuestos)
            detalles.append(detalle)
        return detalles


    def generate_xml_invoice(self):
        """
        """
        factura = etree.Element('factura')
        factura.set("id", "comprobante")
        factura.set("version", "1.1.0")

        # generar infoTributaria
        infoTributaria = self.get_tax_element()
        factura.append(infoTributaria)

        # generar infoFactura
        infoFactura = self.get_invoice_element()
        factura.append(infoFactura)

        #generar detalles
        detalles = self.get_detail_element()
        factura.append(detalles)
        return factura

    def generate_access_key(self):
        f = self.invoice_date.strftime('%d%m%Y')
        t_cbte = tipoDocumento[self.type]
        ruc = self.company.party.vat_number
        #t_amb=proxy.SriService.get_active_env()
        t_amb=self.company.tipo_de_ambiente
        n_cbte= self.number
        cod= "13246587"
        t_ems= self.company.emission_code
        numero_cbte= n_cbte.replace('-','')
        #unimos todos los datos en una sola cadena
        key_temp=f+t_cbte+ruc+t_amb+numero_cbte+cod+t_ems
        #recorremos la cadena para ir guardando en una lista de enteros
        key = []
        for c in key_temp:
            key.append(int(c))
        key.reverse()
        factor = [2,3,4,5,6,7]
        stage1 = sum([n*factor[i%6] for i,n in enumerate(key)])
        stage2 = stage1 % 11
        digit = 11 - (stage2)
        if digit == 11:
            digit =0
        if digit == 10:
            digit = 1
        digit=str(digit)
        access_key= key_temp + digit
        return access_key

    def check_before_sent(self):
        """
        """
        sql = "select autorizado_sri, number from account_invoice where state='open' and number < '%s' order by number desc limit 1" % self.number
        self.execute(sql)
        res = self.fetchone()
        return res[0] and True or False

    def action_generate_invoice(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error de datos de conexión al autorizador de \nfacturacion electrónica.\nVerifique: USUARIO Y CONTRASEÑA .'
        ACTIVE_ERROR = u"Ud. no se encuentra activo, verifique su pago. \nComuníquese con NODUX"
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben ser enviados al SRI para su autorización, en un plazo máximo de 24 horas'

        #for obj in self.browse(self.id):
            # Codigo de acceso
        if not self.type in [ 'out_invoice', 'out_credit_note']:
            pass
        # Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.invoice_date
        date= Date.today()
        limit= (date-date_f).days
        #if limit > 1:
         #   self.raise_user_error(MESSAGE_TIME_LIMIT)

            # Validar que el envio de los comprobantes electronicos sea secuencial
        #if not self.check_before_sent():
            #self.raise_user_error(TITLE_NOT_SENT, MESSAGE_SEQUENCIAL)

        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)
        if self.type == 'out_invoice':
            name = self.company.party.name
            name_l=name.lower()
            name_l=name_l.replace(' ','_')
            name_r = self.replace_charter(name_l)
            name_c = name_r+'.p12'

            authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
            if authenticate == '1':
                pass
            else:
                self.raise_user_error(AUTHENTICATE_ERROR)

            if active == '1':
                self.raise_user_error(ACTIVE_ERROR)
            else:
                pass

            nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
            """
            shutil.copy2(name_c, nuevaruta)
            os.remove(name_c)
            """
            factura1 = self.generate_xml_invoice()
            factura = etree.tostring(factura1, encoding = 'utf8', method = 'xml')
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(factura, 'out_invoice', {})
            if a:
                self.raise_user_error(a)
            file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
            file_check = (nuevaruta+'/'+name_c)
            password = self.company.password_pk12
            error = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
            if error == '1':
                self.raise_user_error('No se ha encontrado el archivo de firma digital (.p12)')

            signed_document= s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(factura, file_pk12, password,{})

            #envio al sri para recepcion del comprobante electronico
            print "Documento ", signed_document
            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
            if result != True:
                self.raise_user_error(result)
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_r, 'out_invoice', signed_document,{})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == 'NO AUTORIZADO':
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
            else:
                pass
            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        else:
            if self.type == 'out_credit_note':
                name = self.company.party.name
                name_l=name.lower()
                name_l=name_l.replace(' ','_')
                name_r = self.replace_charter(name_l)
                name_c = name_r+'.p12'

                if self.company.file_pk12:
                    archivo = self.company.file_pk12
                else :
                    self.raise_user_error(PK12)
                """
                f = open(name_c, 'wb')
                f.write(archivo)
                f.close()
                """
                authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})

                if authenticate == '1':
                    pass
                else:
                    self.raise_user_error(AUTHENTICATE_ERROR)

                if active == '1':
                    self.raise_user_error(ACTIVE_ERROR)
                else:
                    pass

                nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
                """
                shutil.copy2(name_c, nuevaruta)
                os.remove(name_c)
                """
                # XML del comprobante electronico: nota de credito
                notaCredito1 = self.generate_xml_credit_note()
                notaCredito = etree.tostring(notaCredito1, encoding = 'utf8', method = 'xml')
                a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(notaCredito, 'out_credit_note', {})
                if a:
                    self.raise_user_error(a)
                #s.model.nodux_electronic_invoice_auth.conexionescount_voucher('out_invoice',{})
                file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
                file_check = (nuevaruta+'/'+name_c)
                password = self.company.password_pk12
                error = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
                if error == '1':
                    self.raise_user_error('No se ha encontrado el archivo de firma digital (.p12)')
                signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(notaCredito, file_pk12, password,{})
                #envio al sri para recepcion del comprobante electronico
                result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
                if result != True:
                    self.raise_user_error(result)
                time.sleep(WAIT_FOR_RECEIPT)
                # solicitud al SRI para autorizacion del comprobante electronico
                doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_l, 'out_credit_note',{})
                if doc_xml is None:
                    msg = ' '.join(m)
                    raise m

                if auth == False:
                    self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                    self.raise_user_error(m)
                else:
                    pass

                self.send_mail_invoice(doc_xml,access_key, send_m, s)
        return access_key

    def elimina_tildes(self,s):
        return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

    def send_mail_invoice(self, xml_element, access_key, send_m, s, server="localhost"):
        MAIL= u"Ud no ha configurado el correo del cliente. Diríjase a: \nTerceros->General->Medios de Contacto"
        pool = Pool()
        empresa = self.replace_charter(self.company.party.name) #cambiado por self.elimina_tildes(self.company.party.name)
        #empresa = unicode(empresa, 'utf-8')
        empresa = str(self.elimina_tildes(empresa))
        empresa = empresa.replace(' ','_')
        empresa = empresa.lower()

        ahora = datetime.datetime.now()
        year = str(ahora.year)
        client = self.replace_charter(self.party.name) #reemplazo self.party.name
        client = client.upper()
        empresa_ = self.replace_charter(self.company.party.name) #reemplazo self.company.party.name
        ruc = self.company.party.vat_number
        if ahora.month < 10:
            month = '0'+ str(ahora.month)
        else:
            month = str(ahora.month)

        tipo_comprobante = self.type
        if tipo_comprobante == 'out_invoice':
            tipo = 'fact_'
            n_tipo = "FACTURA"
        if tipo_comprobante == 'in_withholding':
            tipo = 'c_r_'
            n_tipo = "COMPROBANTE DE RETENCION"
        if tipo_comprobante == 'out_credit_note':
            tipo = 'n_c_'
            n_tipo = "NOTA DE CREDITO"
        if tipo_comprobante == 'out_debit_note':
            tipo = 'n_d_'
            n_tipo = "NOTA DE DEBITO"

        ruc = access_key[10:23]
        est = access_key[24:27]
        emi= access_key[27:30]
        sec = access_key[30:39]
        num_fac = est+'-'+emi+'-'+sec
        numero = ruc+'_'+num_fac
        name_pdf = tipo+numero+ '.pdf'
        name_xml = tipo+numero + '.xml'
        #nuevaruta =os.getcwd() +'/comprobantes/'+empresa+'/'+year+'/'+month +'/'
        nr = s.model.nodux_electronic_invoice_auth.conexiones.path_files(ruc, {})
        nuevaruta = nr +empresa+'/'+year+'/'+month +'/'

        new_save = 'comprobantes/'+empresa+'/'+year+'/'+month +'/'
        self.write([self],{'estado_sri': 'AUTORIZADO', 'path_xml': new_save+name_xml,'numero_autorizacion' : access_key, 'path_pdf':new_save+name_pdf})

        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        InvoiceReport = Pool().get('account.invoice', type='report')
        report = InvoiceReport.execute([self.id], {})

        email=''
        cont = 0
        for c in correo:
            if c.party == self.party:
                email = c.value
            if c.party == self.company.party:
                cont = cont +1
                f_e = c.value

        if email != '':
            to_email= email
        else :
            self.raise_user_error(MAIL)

        if send_m == '1':
            from_email = f_e
        else :
            from_email = "nodux.ec@gmail.com"
        name = access_key + ".xml"
        reporte = xmlrpclib.Binary(report[1])
        xml_element = unicode(xml_element, 'utf-8')
        xml_element = self.elimina_tildes(xml_element)
        xml = xmlrpclib.Binary(xml_element.replace('><', '>\n<'))

        save_files = s.model.nodux_electronic_invoice_auth.conexiones.save_file(empresa, name_pdf, name_xml, reporte, xml,{})
        p_xml = nuevaruta + name_xml
        p_pdf = nuevaruta + name_pdf
        s.model.nodux_electronic_invoice_auth.conexiones.send_mail(name_pdf, name, p_xml, p_pdf, from_email, to_email, n_tipo, num_fac, client, empresa_, ruc, {})

        return True

    def get_credit_note_element(self):

        pool = Pool()
        company = self.company
        Sale = pool.get('sale.sale')
        Invoice = pool.get('account.invoice')
        motivo='Emitir factura con el mismo concepto'
        sales = Sale.search([('reference', '=', self.description), ('reference', '!=', None)])

        for s in sales:
            sale = s
            if sale.motivo:
                motivo = sale.motivo
        invoices = Invoice.search([('description', '=', sale.description), ('description', '!=', None), ('type', '=', 'out_invoice')])
        for i in invoices:
            invoice = i
        infoNotaCredito = etree.Element('infoNotaCredito')
        etree.SubElement(infoNotaCredito, 'fechaEmision').text = self.invoice_date.strftime('%d/%m/%Y')
        #etree.subElement(infoNotaCredito, 'dirEstablecimiento').text = self.company.party.address[0]
        if self.party.type_document:
            etree.SubElement(infoNotaCredito, 'tipoIdentificacionComprador').text = tipoIdentificacion[self.party.type_document]
        else:
            self.raise_user_error("No ha configurado el tipo de identificacion del cliente")
        etree.SubElement(infoNotaCredito, 'razonSocialComprador').text = self.replace_charter(self.party.name) #self.party.name
        etree.SubElement(infoNotaCredito, 'identificacionComprador').text = self.party.vat_number
        #etree.SubElement(infoNotaCredito, 'contribuyenteEspecial').text = company.company_registry
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoNotaCredito, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoNotaCredito, 'obligadoContabilidad').text = 'NO'
        move = self.move
        etree.SubElement(infoNotaCredito, 'rise').text = tipoDocumento[move.origin.type]
        etree.SubElement(infoNotaCredito, 'codDocModificado').text = '01'
        etree.SubElement(infoNotaCredito, 'numDocModificado').text = invoice.number
        etree.SubElement(infoNotaCredito, 'fechaEmisionDocSustento').text = s.sale_date.strftime('%d/%m/%Y')
        etree.SubElement(infoNotaCredito, 'totalSinImpuestos').text = '%.2f'%(self.untaxed_amount)
        etree.SubElement(infoNotaCredito, 'valorModificacion').text = '%.2f'%(self.total_amount)
        etree.SubElement(infoNotaCredito, 'moneda').text = 'DOLAR'
        #totalConImpuestos
        totalConImpuestos = etree.Element('totalConImpuestos')
        for tax in self.taxes:
            totalImpuesto = etree.Element('totalImpuesto')
            etree.SubElement(totalImpuesto, 'codigo').text = "2"
            if str('{:.0f}'.format(tax.tax.rate*100)) == '12':
                codigoPorcentaje = '2'
            if str('{:.0f}'.format(tax.tax.rate*100)) == '0':
                codigoPorcentaje = '0'
            if str('{:.0f}'.format(tax.tax.rate*100)) == '14':
                codigoPorcentaje = '3'
            if tax.tax.rate == None:
                codigoPorcentaje = '6'
            etree.SubElement(totalImpuesto, 'codigoPorcentaje').text = codigoPorcentaje
            etree.SubElement(totalImpuesto, 'baseImponible').text = '{:.2f}'.format(tax.base)
            etree.SubElement(totalImpuesto, 'valor').text = '{:.2f}'.format(tax.amount)
            totalConImpuestos.append(totalImpuesto)

        infoNotaCredito.append(totalConImpuestos)
        etree.SubElement(infoNotaCredito, 'motivo').text= motivo
        return infoNotaCredito
    #detalles de nota de credito
    def get_detail_credit_note(self):

        def fix_chars(code):
            if code:
                code.replace(u'%',' ').replace(u'º',' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                code = ''.join((c for c in unicodedata.normalize('NFD', code) if unicodedata.category(c) != 'Mn'))
                return code
            return '1'

        detalles = etree.Element('detalles')
        for line in self.lines:
            pool = Pool()
            Taxes1 = pool.get('product.category-customer-account.tax')
            Taxes2 = pool.get('product.template-customer-account.tax')

            detalle = etree.Element('detalle')
            etree.SubElement(detalle, 'codigoInterno').text = fix_chars(line.product.code)
            etree.SubElement(detalle, 'descripcion').text = self.replace_charter(line.description) #fix_chars(line.description)
            etree.SubElement(detalle, 'cantidad').text = '%.2f' % (line.quantity)
            etree.SubElement(detalle, 'precioUnitario').text = '%.2f' % (line.unit_price)
            etree.SubElement(detalle, 'descuento').text = '0.00'
            etree.SubElement(detalle, 'precioTotalSinImpuesto').text = '%.2f' % (line.amount)
            impuestos = etree.Element('impuestos')
            impuesto = etree.Element('impuesto')
            etree.SubElement(impuesto, 'codigo').text = "2"

            if line.product.iva_category == True:
                codigoPorcentaje_e_o = line.product.category.iva_tarifa
            else:
                codigoPorcentaje_e_o = line.product.iva_tarifa

            if line.product.taxes_category == True:
                if line.product.category.taxes_parent == True:
                    taxes1= Taxes1.search([('category','=', line.product.category.parent)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                else:
                    taxes1= Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
            else:
                taxes1= Taxes1.search([('category','=', line.product.category)])
                taxes2 = Taxes2.search([('product','=', line.product)])
                taxes3 = Taxes2.search([('product','=', line.product.template)])

            if taxes1:
                for t in taxes1:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                    if t.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            elif taxes2:
                for t in taxes2:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                        codigo = '2'
                    if str('{:.0f}'.format(tax.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                        codigo = '2'
                    if str('{:.0f}'.format(tax.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                        codigo = '2'
                    if tax.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            elif taxes3:
                for t in taxes3:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        codigoPorcentaje = '2'
                        codigo = '2'
                    if str('{:.0f}'.format(tax.tax.rate*100)) == '0':
                        codigoPorcentaje = '0'
                        codigo = '2'
                    if str('{:.0f}'.format(tax.tax.rate*100)) == '14':
                        codigoPorcentaje = '3'
                        codigo = '2'
                    if tax.tax.rate == None:
                        codigoPorcentaje = '6'
                    etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                    etree.SubElement(impuesto, 'tarifa').text = str('{:.0f}'.format(t.tax.rate*100))
                    etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(line.amount)
                    etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(line.amount*(t.tax.rate))
                impuestos.append(impuesto)
            detalle.append(impuestos)
            detalles.append(detalle)
        return detalles

    #generar nota de Credito
    def generate_xml_credit_note(self):
        notaCredito = etree.Element('notaCredito')
        notaCredito.set("id", "comprobante")
        notaCredito.set("version", "1.1.0")

        # generar infoTributaria
        infoTributaria = self.get_tax_element()
        notaCredito.append(infoTributaria)

        #generar infoNotaCredito
        infoNotaCredito = self.get_credit_note_element()
        notaCredito.append(infoNotaCredito)

        #generar detalles
        detalles = self.get_detail_credit_note()
        notaCredito.append(detalles)
        print etree.tostring(notaCredito, pretty_print=True, xml_declaration=True, encoding="utf-8")
        return notaCredito

    #withholding (comprobante de retencion)
    def get_invoice_element_w(self):
        """
        """
        company = self.company
        party = self.party
        infoCompRetencion = etree.Element('infoCompRetencion')
        etree.SubElement(infoCompRetencion, 'fechaEmision').text = self.invoice_date.strftime('%d/%m/%Y')
        #etree.SubElement(infoFactura, 'dirEstablecimiento').text = self.company.party.addresses
        #if self.company:
         #   etree.SubElement(infoFactura, 'contribuyenteEspecial').text = self.company
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoCompRetencion, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoCompRetencion, 'obligadoContabilidad').text = 'NO'
        if self.party.type_document:
            etree.SubElement(infoCompRetencion, 'tipoIdentificacionSujetoRetenido').text = tipoIdentificacion[self.party.type_document]
        else:
            self.raise_user_error("No ha configurado el tipo de identificacion del cliente")
        etree.SubElement(infoCompRetencion, 'razonSocialSujetoRetenido').text = 'PRUEBAS SERVICIO DE RENTAS INTERNAS'
        #self.party.name
        etree.SubElement(infoCompRetencion, 'identificacionSujetoRetenido').text = self.party.vat_number
        etree.SubElement(infoCompRetencion, 'periodoFiscal').text = self.move.period.start_date.strftime('%m/%Y')
        return infoCompRetencion

    #obtener impuestos (plan de cuentas, impuestos)
    #cuando los impuestos sean negativos multiplicar rate*-100 y tax.amount*-1
    def get_taxes(self):
        impuestos = etree.Element('impuestos')
        for tax in self.taxes:
            fecha = str(self.ambiente).replace('-','/')
            m = fecha[8:10]
            d = fecha[5:7]
            y = fecha[0:4]

            impuesto = etree.Element('impuesto')
            etree.SubElement(impuesto, 'codigo').text = tax.tax.code_withholding
            etree.SubElement(impuesto, 'codigoRetencion').text = tax.tax.code_electronic.code
            etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(tax.base)
            etree.SubElement(impuesto, 'porcentajeRetener').text= '{:.0f}'.format(tax.tax.rate*(-100))
            etree.SubElement(impuesto, 'valorRetenido').text= '{:.2f}'.format(tax.amount*(-1))
            etree.SubElement(impuesto, 'codDocSustento').text="01"
            etree.SubElement(impuesto, 'numDocSustento').text=(self.number_w).replace('-','')
            etree.SubElement(impuesto, 'fechaEmisionDocSustento').text= (m+'/'+d+'/'+y)
            impuestos.append(impuesto)
        return impuestos

    #generar comprobante de retencion
    def generate_xml_invoice_w(self):
        comprobanteRetencion = etree.Element('comprobanteRetencion')
        comprobanteRetencion.set("id", "comprobante")
        comprobanteRetencion.set("version", "1.0.0")
        # generar infoTributaria
        infoTributaria = self.get_tax_element()
        comprobanteRetencion.append(infoTributaria)
        # generar infoCompRetencion
        infoCompRetencion = self.get_invoice_element_w()
        comprobanteRetencion.append(infoCompRetencion)
        #generar impuestos
        impuestos = self.get_taxes()
        comprobanteRetencion.append(impuestos)
        return comprobanteRetencion

    def action_generate_invoice_w(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben ser enviados al SRI para su autorización, en un plazo máximo de 24 horas'

        #for obj in self.browse(self.id):
            # Codigo de acceso
        if not self.type in ['in_withholding']:
            pass
        # Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.invoice_date
        date= Date.today()
        limit= (date-date_f).days
        #if limit > 1:
         #   self.raise_user_error(MESSAGE_TIME_LIMIT)

            # Validar que el envio de los comprobantes electronicos sea secuencial
        #if not self.check_before_sent():
            #self.raise_user_error(TITLE_NOT_SENT, MESSAGE_SEQUENCIAL)

        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        if self.type == 'in_withholding':
            name = self.company.party.name
            name_l=name.lower()
            name_l=name_l.replace(' ','_')
            name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
            name_c = name_r+'.p12'

            if self.company.file_pk12:
                archivo = self.company.file_pk12
            else :
                self.raise_user_error(PK12)
            f = open(name_c, 'wb')
            f.write(archivo)
            f.close()
            authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
            if authenticate == '1':
                pass
            else:
                self.raise_user_error(AUTHENTICATE_ERROR)

            if active == '1':
                self.raise_user_error(ACTIVE_ERROR)
            else:
                pass

            nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
            shutil.copy2(name_c, nuevaruta)
            os.remove(name_c)

            # XML del comprobante electronico: factura
            comprobanteRetencion1 = self.generate_xml_invoice_w()
            #validacion del xml (llama metodo validate xml de sri)
            comprobanteRetencion = etree.tostring(comprobanteRetencion1, encoding = 'utf8', method = 'xml')
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(comprobanteRetencion, 'in_withholding', {})
            if a:
                self.raise_user_error(a)
            file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
            password = self.company.password_pk12
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(comprobanteRetencion, file_pk12, password,{})
            #envio al sri para recepcion del comprobante electronico
            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
            if result != True:
                self.raise_user_error(result)
            #s.model.nodux_electronic_invoice_auth.conexionescount_voucher('in_withholding', {})
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_l, 'in_withholding',{})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m
            no_auth = 'NO AUTORIZADO'

            if auth == False:
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                self.raise_user_error(m)
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key, send_m)

            return access_key

    #nota de debito
    def get_debit_note_element(self):
        """
        """
        pool = Pool()
        num_mod=self.number_w
        Invoices = pool.get('account.invoice')
        invoice = Invoices.search([('number','=',num_mod)])
        for i in invoice:
            date_m = i.invoice_date.strftime('%d/%m/%Y')
        fecha = str(self.ambiente).replace('-','/')
        m = fecha[8:10]
        d = fecha[5:7]
        y = fecha[0:4]

        company = self.company
        infoNotaDebito = etree.Element('infoNotaDebito')
        etree.SubElement(infoNotaDebito, 'fechaEmision').text = self.invoice_date.strftime('%d/%m/%Y')
        #etree.subElement(infoNotaCredito, 'dirEstablecimiento').text = self.company.party.address[0]
        if self.party.type_document:
            etree.SubElement(infoNotaDebito, 'tipoIdentificacionComprador').text = tipoIdentificacion[self.party.type_document]
        else:
            self.raise_user_error("No ha configurado el tipo de identificacion del cliente")
        etree.SubElement(infoNotaDebito, 'razonSocialComprador').text = self.replace_charter(self.party.name) #self.party.name
        etree.SubElement(infoNotaDebito, 'identificacionComprador').text = self.party.vat_number
        #etree.SubElement(infoNotaCredito, 'contribuyenteEspecial').text = company.company_registry
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoNotaDebito, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoNotaDebito, 'obligadoContabilidad').text = 'NO'
        etree.SubElement(infoNotaDebito, 'rise').text = 'Contribuyente Rise'
        etree.SubElement(infoNotaDebito, 'codDocModificado').text = '01'
        etree.SubElement(infoNotaDebito, 'numDocModificado').text = self.number_w
        etree.SubElement(infoNotaDebito, 'fechaEmisionDocSustento').text = (m+'/'+d+'/'+y)
        #line.origin.invoice.invoice_date.strftime('%d/%m/%Y')
        etree.SubElement(infoNotaDebito, 'totalSinImpuestos').text = '%.2f'%(self.untaxed_amount)
        #totalConImpuestos
        impuestos = etree.Element('impuestos')
        for tax in self.taxes:
                impuesto = etree.Element('impuesto')
                etree.SubElement(impuesto, 'codigo').text = "2"
                if str('{:.0f}'.format(tax.tax.rate*100)) == '12':
                    codigoPorcentaje = '2'
                if str('{:.0f}'.format(tax.tax.rate*100)) == '0':
                    codigoPorcentaje = '0'
                if tax.tax.rate == None:
                    codigoPorcentaje = '6'
                etree.SubElement(impuesto, 'codigoPorcentaje').text = codigoPorcentaje
                etree.SubElement(impuesto, 'tarifa').text = "12"
                etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(tax.base)
                etree.SubElement(impuesto, 'valor').text = '{:.2f}'.format(tax.amount)
                impuestos.append(impuesto)

        infoNotaDebito.append(impuestos)
        etree.SubElement(infoNotaDebito, 'valorTotal').text = '{:.2f}'.format(self.total_amount)
        return infoNotaDebito

        #detalles de nota de debito

    def get_detail_debit_note(self):

        def fix_chars(code):
            if code:
                code.replace(u'%',' ').replace(u'º',' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                code = ''.join((c for c in unicodedata.normalize('NFD', code) if unicodedata.category(c) != 'Mn'))
                return code
            return '1'

        motivos = etree.Element('motivos')
        for line in self.lines:
            motivo = etree.Element('motivo')
            etree.SubElement(motivo, 'razon').text = self.replace_charter(line.description) #fix_chars(line.description)
            etree.SubElement(motivo, 'valor').text = '%.2f' % (line.unit_price)
            motivos.append(motivo)
        return motivos

    def generate_xml_debit_note(self):

        notaDebito = etree.Element('notaDebito')
        notaDebito.set("id", "comprobante")
        notaDebito.set("version", "1.0.0")

        # generar infoTributaria
        infoTributaria = self.get_tax_element()
        notaDebito.append(infoTributaria)

        #generar infoNotaCredito
        infoNotaDebito = self.get_debit_note_element()
        notaDebito.append(infoNotaDebito)

        #generar detalles
        motivos = self.get_detail_debit_note()
        notaDebito.append(motivos)

        return notaDebito

    #consumir ws sri, llamar método de firma obtener datos del SRI
    def action_generate_debit_note(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben ser enviados al SRI para su autorización, en un plazo máximo de 24 horas'

        #for obj in self.browse(self.id):
            # Codigo de acceso
        if not self.type in [ 'out_debit_note']:
            pass
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.invoice_date
        date= Date.today()
        limit= (date-date_f).days
        # Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision

        #if limit > 1:
         #   self.raise_user_error(MESSAGE_TIME_LIMIT)

            # Validar que el envio de los comprobantes electronicos sea secuencial
        #if not self.check_before_sent():
            #self.raise_user_error(TITLE_NOT_SENT, MESSAGE_SEQUENCIAL)
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        #self.write(self.id, {'clave_acceso': access_key, 'emission_code': emission_code})

        if self.type == 'out_debit_note':
            name = self.company.party.name
            name_l = name.lower()
            name_l=name_l.replace(' ','_')
            name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
            name_c = name_r+'.p12'

            if self.company.file_pk12:
                archivo = self.company.file_pk12
            else :
                self.raise_user_error(PK12)

            f = open(name_c, 'wb')
            f.write(archivo)
            f.close()
            authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
            if authenticate == '1':
                pass
            else:
                self.raise_user_error(AUTHENTICATE_ERROR)
            if active == '1':
                self.raise_user_error(ACTIVE_ERROR)
            else:
                pass

            nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
            shutil.copy2(name_c, nuevaruta)
            os.remove(name_c)
            # XML del comprobante electronico: factura
            notaDebito1 = self.generate_xml_debit_note()
            notaDebito = etree.tostring(notaDebito1, encoding = 'utf8', method = 'xml')
            #validacion del xml (llama metodo validate xml de sri)
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(notaDebito, 'out_debit_note', {})
            if a:
                self.raise_user_error(a)
            file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
            password = self.company.password_pk12
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(notaDebito, file_pk12, password,{})
            #envio al sri para recepcion del comprobante electronico
            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
            if result != True:
                self.raise_user_error(result)
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_l, 'out_debit_note',{})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m
            #self.send_mail_invoice(self, doc_xml, auth,
            if auth == False:
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                self.raise_user_error(m)
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key, send_m)

            return access_key


    def generate_xml_lote(self):
        pool = Pool()
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)
        name = self.company.party.name
        name_l = name.lower()
        name_l=name_l.replace(' ','_')
        name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
        name_c = name_r+'.p12'
        """
        if self.company.file_pk12:
            archivo = self.company.file_pk12
        else :
            self.raise_user_error(PK12)

        f = open(name_c, 'wb')
        f.write(archivo)
        f.close()
        """

        authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
        if authenticate == '1':
            pass
        else:
            self.raise_user_error(AUTHENTICATE_ERROR)

        if active == '1':
            self.raise_user_error(ACTIVE_ERROR)
        else:
            pass

        nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})

        """
        shutil.copy2(name_c, nuevaruta)
        os.remove(name_c)
        """
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        password = self.company.password_pk12


        Invoice = pool.get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for invoice in invoices:
            factura1 = invoice.generate_xml_invoice()
            factura = etree.tostring(factura1, encoding = 'utf8', method = 'xml')
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(factura, file_pk12, password,{})
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote

    def action_generate_lote(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        ACTIVE_ERROR = u"Ud. no se encuentra activo, verifique su pago. \nComuníquise con NODUX"
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben ser enviados al SRI para su autorización, en un plazo máximo de 24 horas'

        if not self.type in ['out_invoice']:
            pass
        # Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.invoice_date
        date= Date.today()
        limit= (date-date_f).days
        #if limit > 1:
         #   self.raise_user_error(MESSAGE_TIME_LIMIT)

            # Validar que el envio de los comprobantes electronicos sea secuencial
        #if not self.check_before_sent():
            #self.raise_user_error(TITLE_NOT_SENT, MESSAGE_SEQUENCIAL)
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        if self.type == 'out_invoice':
            name = self.company.party.name
            name_l=name.lower()
            name_l=name_l.replace(' ','_')
            name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
            print "El nombre ", name_r
            name_c = name_r+'.p12'
            """
            if self.company.file_pk12:
                archivo = self.company.file_pk12
            else :
                self.raise_user_error(PK12)

            f = open(name_c, 'wb')
            f.write(archivo)
            f.close()
            """
            authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
            if authenticate == '1':
                pass
            else:
                self.raise_user_error(AUTHENTICATE_ERROR)

            if active == '1':
                self.raise_user_error(ACTIVE_ERROR)
            else:
                pass

            nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})

            """
            shutil.copy2(name_c, nuevaruta)
            os.remove(name_c)
            """
            # XML del comprobante electronico: factura
            lote1 = self.generate_xml_lote()
            lote = etree.tostring(lote1, encoding = 'utf8', method ='xml')
            #validacion del xml (llama metodo validate xml de sri)
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(lote, 'lote', {})
            if a:
                self.raise_user_error(a)
            file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
            file_check = (nuevaruta+'/'+name_c)
            password = self.company.password_pk12
            error  = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
            if error == '1':
                self.raise_user_error('No se ha encontrado el archivo de la firma digital(.p12)')

            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(lote, {})
            if result != True:
                self.raise_user_error(result)
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization_lote(access_key, name_r, 'lote_out_invoice',{})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == 'NO AUTORIZADO':
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        return access_key


    def generate_xml_lote_w(self):

        pool = Pool()
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)
        name = self.company.party.name
        name_l=name.lower()
        name_l=name_l.replace(' ','_')
        name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
        name_c = name_r+'.p12'

        if self.company.file_pk12:
            archivo = self.company.file_pk12
        else :
            self.raise_user_error(PK12)

        f = open(name_c, 'wb')
        f.write(archivo)
        f.close()
        authenticate, send_m = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
        if authenticate == '1':
            pass
        else:
            self.raise_user_error(AUTHENTICATE_ERROR)

        nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
        shutil.copy2(name_c, nuevaruta)
        os.remove(name_c)
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        password = self.company.password_pk12


        Invoice = pool.get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for invoice in invoices:
            comprobanteRetencion1 = self.generate_xml_invoice_w()
            comprobanteRetencion = etree.tostring(comprobanteRetencion1, encoding = 'utf8', method = 'xml')
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(factura, file_pk12, password,{})
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote

    def action_generate_lote_w(self):
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben ser enviados al SRI para su autorización, en un plazo máximo de 24 horas'
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        if self.type == 'in_withholding':
            name = self.company.party.name
            name_l=name.lower()
            name_l=name_l.replace(' ','_')
            name_r = self.replace_charter(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
            name_c = name_r+'.p12'

            if self.company.file_pk12:
                archivo = self.company.file_pk12
            else :
                self.raise_user_error(PK12)

            f = open(name_c, 'wb')
            f.write(archivo)
            f.close()
            authenticate, send_m = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
            if authenticate == '1':
                pass
            else:
                self.raise_user_error(AUTHENTICATE_ERROR)

            nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
            shutil.copy2(name_c, nuevaruta)
            os.remove(name_c)
            # XML del comprobante electronico: factura
            lote = self.generate_xml_lote()
            #validacion del xml (llama metodo validate xml de sri)
            inv_xml = DocumentXML(lote, 'lote')
            inv_xml.validate_xml()
            # solicitud de autorizacion del comprobante electronico
            xmlstr = etree.tostring(lote, encoding='utf8', method='xml')
            inv_xml.send_receipt(xmlstr)
            time.sleep(WAIT_FOR_RECEIPT)
            doc_xml, m, auth = inv_xml.request_authorization_lote(key)
            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == False:
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                self.raise_user_error(m)
            else:
                pass
            self.send_mail_invoice(doc_xml, access_key)

        return key


        if self.type == 'out_invoice':

            # XML del comprobante electronico: factura
            lote1 = self.generate_xml_lote()
            lote = etree.tostring(lote1, encoding = 'utf8', method ='xml')
            #validacion del xml (llama metodo validate xml de sri)
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(lote, 'lote', {})
            if a:
                self.raise_user_error(a)

            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(lote, {})
            if result != True:
                self.raise_user_error(result)
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization_lote(access_key, name_l, 'lote_out_invoice',{})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == False:
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                self.raise_user_error(m)
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key, send_m)

        return access_key

    def generate_xml_lote_debit(self):
        pool = Pool()
        xades = Xades()
        file_pk12 = base64.encodestring(self.company.electronic_signature)
        password = base64.encodestring(self.company.password_hash)
        Invoice = pool.get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])

        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for invoice in invoices:
            notaDebito = self.generate_xml_debit_note()
            signed_document = xades.apply_digital_signature(notaDebito, file_pk12, password)
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote

    def action_generate_lote_debit(self):
        LIMIT_TO_SEND = 5
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electronicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Los comprobantes electronicos deben ser enviados al SRI para su autorizacion, en un plazo maximo de 24 horas'
        key = self.generate_access_key_lote()
        if self.type == 'out_debit_note':
            # XML del comprobante electronico: factura
            lote = self.generate_xml_lote()
            #validacion del xml (llama metodo validate xml de sri)
            inv_xml = DocumentXML(lote, 'lote')
            inv_xml.validate_xml()
            # solicitud de autorizacion del comprobante electronico
            xmlstr = etree.tostring(lote, encoding='utf8', method='xml')
            inv_xml.send_receipt(xmlstr)
            time.sleep(WAIT_FOR_RECEIPT)
            doc_xml, m, auth = inv_xml.request_authorization_lote(key)
            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == False:
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                self.raise_user_error(m)
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key)
        return key

    def generate_xml_lote_credit(self):
        pool = Pool()
        xades = Xades()
        file_pk12 = base64.encodestring(self.company.electronic_signature)
        password = base64.encodestring(self.company.password_hash)
        Invoice = pool.get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for invoice in invoices:
            notaCredito = self.generate_xml_credit_note()
            signed_document = xades.apply_digital_signature(notaCredito, file_pk12, password)
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote

    def action_generate_lote_credit(self):
        LIMIT_TO_SEND = 5
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electronicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Los comprobantes electronicos deben ser enviados al SRI para su autorizacion, en un plazo maximo de 24 horas'
        key = self.generate_access_key_lote()
        # XML del comprobante electronico: factura
        lote = self.generate_xml_lote_credit()
        #validacion del xml (llama metodo validate xml de sri)
        inv_xml = DocumentXML(lote, 'lote')
        inv_xml.validate_xml()
        # solicitud de autorizacion del comprobante electronico
        xmlstr = etree.tostring(lote, encoding='utf8', method='xml')
        inv_xml.send_receipt(xmlstr)
        time.sleep(WAIT_FOR_RECEIPT)
        doc_xml, m, auth = inv_xml.request_authorization_lote(key)
        if doc_xml is None:
            msg = ' '.join(m)
            raise m

        if auth == False:
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
            self.raise_user_error(m)
        else:
            pass

        self.send_mail_invoice(doc_xml, access_key)

        return key

    def generate_access_key_lote(self):

        fecha = time.strftime('%d%m%Y')
        tipo_cbte = tipoDocumento[self.type]
        ruc = self.company.party.vat_number
        tipo_amb=self.company.tipo_de_ambiente
        n_cbte= self.number
        cod= "13245768"
        t_ems= self.company.emission_code
        numero_cbte= n_cbte.replace('-','')
        #unimos todos los datos en una sola cadena

        tipo_emision= self.company.emission_code

        clave_inicial=fecha + tipo_cbte + ruc + tipo_amb+numero_cbte+ cod + t_ems
        clave = []
        for c in clave_inicial:
            clave.append(int(c))
        clave.reverse()
        factor = [2,3,4,5,6,7]
        etapa1 = sum([n*factor[i%6] for i,n in enumerate(clave)])
        etapa2 = etapa1 % 11
        digito = 11 - (etapa2)
        if digito == 11:
            digito =0
        if digito == 10:
            digito = 1
        digito=str(digito)
        clave_acceso_lote= clave_inicial+digito
        return clave_acceso_lote

class SendSriLoteStart(ModelView):
    'Send Sri Lote Start'
    __name__ = 'nodux.account.electronic.invoice.ec.lote.start'


class SendSriLote(Wizard):
    'Send Sri Lote'
    __name__ = 'nodux.account.electronic.invoice.ec.lote'

    start = StateView('nodux.account.electronic.invoice.ec.lote.start',
        'nodux_account_electronic_invoice_ec.send_sri_lote_start_view_form', [
        Button('Cancel', 'end', 'tryton-cancel'),
        Button('Ok', 'accept', 'tryton-ok', default=True),
        ])
    accept = StateTransition()

    def transition_accept(self):
        Invoice = Pool().get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        for invoice in invoices:
            if invoice.estado_sri == 'AUTORIZADO':
                pass

            else:
                if invoice.type == u'out_invoice':
                    invoice.generate_xml_lote()
                    invoice.action_generate_lote()
                    invoice.generate_access_key_lote()
                    invoice.connect_db()

                elif invoice.type == u'out_credit_note':
                    invoice.generate_xml_lote_credit()
                    invoice.action_generate_lote_credit()
                    invoice.connect_db()


                elif invoice.type == u'in_invoice':
                    Withholding = Pool().get('account.withholding')
                    withholdings = Withholding.search([('number'), '=', invoice.ref_withholding])
                    for withholding in withholdings:
                    #invoice.authenticate()
                        withholding.get_invoice_element_w()
                        withholding.get_tax_element()
                        withholding.generate_xml_invoice_w()
                        withholding.get_taxes()
                        withholding.action_generate_invoice_w()
                        withholding.connect_db()
                """
                elif invoice.type == 'out_debit_note':
                    invoice.generate_xml_lote_debit()
                    invoice.action_generate_lote_debit()
                    invoice.connect_db()
                """
        return 'end'

class InvoiceReport(Report):
    __name__ = 'account.invoice'

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        User = pool.get('res.user')
        Invoice = pool.get('account.invoice')

        invoice = records[0]

        user = User(Transaction().user)
        localcontext['company'] = user.company
        localcontext['vat_number'] = cls._get_vat_number(user.company)
        if invoice.type == 'in_invoice':
            pass
        else:
            if invoice.numero_autorizacion:
                localcontext['barcode_img']=cls._get_barcode_img(Invoice, invoice)
        localcontext['vat_number_cliente'] = cls._get_vat_number_cliente(Invoice, invoice)
        localcontext['subtotal_12'] = cls._get_subtotal_12(Invoice, invoice)
        localcontext['subtotal_0'] = cls._get_subtotal_0(Invoice, invoice)
        localcontext['subtotal_14'] = cls._get_subtotal_14(Invoice, invoice)
        localcontext['numero'] = cls._get_numero(Invoice, invoice)
        localcontext['fecha'] = cls._get_fecha(Invoice, invoice)
        localcontext['motivo'] = cls._get_motivo(Invoice, invoice)

        return super(InvoiceReport, cls).parse(report, records, data,
                localcontext=localcontext)

    @classmethod
    def _get_numero(cls, Invoice, invoice):
        numero = ""
        pool = Pool()
        Sale = pool.get('sale.sale')
        sales = Sale.search([('reference', '=', invoice.description), ('reference', '!=', None)])
        if sales:
            for s in sales:
                sale = s
            invoices = Invoice.search([('description', '=', sale.description), ('description', '!=', None)])
            if invoices:
                for i in invoices:
                    invoice = i
                numero = invoice.number
        return numero

    @classmethod
    def _get_fecha(cls, Invoice, invoice):
        fecha = ""
        pool = Pool()
        Sale = pool.get('sale.sale')
        sales = Sale.search([('reference', '=', invoice.description), ('reference', '!=', None)])
        if sales:
            for s in sales:
                sale = s
            invoices = Invoice.search([('description', '=', sale.description), ('description', '!=', None)])
            if invoices:
                for i in invoices:
                    invoice = i
                fecha = invoice.invoice_date
        return fecha

    @classmethod
    def _get_motivo(cls, Invoice, invoice):
        motivo = 'Emitir factura con el mismo concepto'
        pool = Pool()
        Sale = pool.get('sale.sale')
        sales = Sale.search([('reference', '=', invoice.description), ('reference', '!=', None)])
        if sales:
            for s in sales:
                sale = s
                if sale.motivo:
                    motivo = sale.motivo
        return motivo

    @classmethod
    def _get_vat_number_cliente(cls, Invoice, invoice):
        value = invoice.party.vat_number
        if value:
            return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])
        return ''

    @classmethod
    def _get_vat_number(cls, company):
        value = company.party.vat_number
        return '%s-%s-%s' % (value[:2], value[2:-1], value[-1])


    @classmethod
    def _get_barcode_img(cls, Invoice, invoice):
        from barras import CodigoBarra
        from cStringIO import StringIO as StringIO
        # create the helper:
        codigobarra = CodigoBarra()
        output = StringIO()
        bars= invoice.numero_autorizacion
        codigobarra.GenerarImagen(bars, output, basewidth=3, width=380, height=50, extension="PNG")
        image = buffer(output.getvalue())
        output.close()
        return image

    @classmethod
    def _get_subtotal_12(cls, Invoice, invoice):
        subtotal12 = Decimal(0.00)
        pool = Pool()
        Taxes1 = pool.get('product.category-customer-account.tax')
        Taxes2 = pool.get('product.template-customer-account.tax')

        for line in invoice.lines:
            if line.product.taxes_category == True:
                if line.product.category.taxes_parent == True:
                    taxes1= Taxes1.search([('category','=', line.product.category.parent)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                else:
                    taxes1= Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
            else:
                taxes1= Taxes1.search([('category','=', line.product.category)])
                taxes2 = Taxes2.search([('product','=', line.product)])
                taxes3 = Taxes2.search([('product','=', line.product.template)])

            if taxes1:
                for t in taxes1:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        subtotal12= subtotal12 + (line.amount)
            elif taxes2:
                for t in taxes2:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        subtotal12= subtotal12 + (line.amount)
            elif taxes3:
                for t in taxes3:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '12':
                        subtotal12= subtotal12 + (line.amount)
        return subtotal12

    @classmethod
    def _get_subtotal_14(cls, Invoice, invoice):
        subtotal14 = Decimal(0.00)
        pool = Pool()
        Taxes1 = pool.get('product.category-customer-account.tax')
        Taxes2 = pool.get('product.template-customer-account.tax')
        for line in invoice.lines:
            if line.product.taxes_category == True:
                if line.product.category.taxes_parent == True:
                    taxes1= Taxes1.search([('category','=', line.product.category.parent)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                else:
                    taxes1= Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
            else:
                taxes1= Taxes1.search([('category','=', line.product.category)])
                taxes2 = Taxes2.search([('product','=', line.product)])
                taxes3 = Taxes2.search([('product','=', line.product.template)])

            if taxes1:
                for t in taxes1:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        subtotal14= subtotal14 + (line.amount)
            elif taxes2:
                for t in taxes2:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        subtotal14= subtotal14 + (line.amount)
            elif taxes3:
                for t in taxes3:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '14':
                        subtotal14= subtotal14 + (line.amount)

        return subtotal14

    @classmethod
    def _get_subtotal_0(cls, Invoice, invoice):
        subtotal0 = Decimal(0.00)
        pool = Pool()
        Taxes1 = pool.get('product.category-customer-account.tax')
        Taxes2 = pool.get('product.template-customer-account.tax')

        for line in invoice.lines:
            if line.product.taxes_category == True:
                if line.product.category.taxes_parent == True:
                    taxes1= Taxes1.search([('category','=', line.product.category.parent)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
                else:
                    taxes1= Taxes1.search([('category','=', line.product.category)])
                    taxes2 = Taxes2.search([('product','=', line.product)])
                    taxes3 = Taxes2.search([('product','=', line.product.template)])
            else:
                taxes1= Taxes1.search([('category','=', line.product.category)])
                taxes2 = Taxes2.search([('product','=', line.product)])
                taxes3 = Taxes2.search([('product','=', line.product.template)])

            if taxes1:
                for t in taxes1:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        subtotal0= subtotal0 + (line.amount)
            elif taxes2:
                for t in taxes2:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        subtotal0= subtotal0 + (line.amount)

            elif taxes3:
                for t in taxes3:
                    if str('{:.0f}'.format(t.tax.rate*100)) == '0':
                        subtotal0= subtotal0 + (line.amount)

        return subtotal0
