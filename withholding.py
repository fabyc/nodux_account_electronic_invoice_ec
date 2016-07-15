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
from trytond.modules.company import CompanyReport
import re

__all__ = ['AccountWithholding', 'PrintWithholdingE']
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
class AccountWithholding():
    'Account Withholding'
    __name__ = 'account.withholding'

    estado_sri = fields.Char('Estado Facturacion-Electronica', size=24, readonly=True)
    path_xml = fields.Char(u'Path archivo xml de comprobante', readonly=True)
    path_pdf = fields.Char(u'Path archivo pdf de comprobante', readonly=True)
    numero_autorizacion = fields.Char(u'Número de Autorización', readonly= True)
    fisic = fields.Boolean('Fisic Withholding', states={
            'invisible': Eval('type') != 'in_withholding',
            'readonly' : Eval('state') != 'draft'
            })

    @classmethod
    def __setup__(cls):
        super(AccountWithholding, cls).__setup__()
        """
        cls._check_modify_exclude = ['estado_sri', 'path_xml', 'numero_autorizacion', 'ambiente','mensaje','path_pdf', 'state', 'payment_lines', 'cancel_move',
                'invoice_report_cache', 'invoice_report_format']
        """
        cls.number.states['readonly'] = ~Eval('fisic',True)
        cls.number.states['required'] = Eval('fisic',True)

    @classmethod
    @ModelView.button
    def validate_withholding(cls, withholdings):
        for withholding in withholdings:
            if withholding.type in ('in_withholding'):
                Invoice = Pool().get('account.invoice')
                invoices = Invoice.search([('number','=',withholding.reference), ('number','!=', None)])
                for i in invoices:
                    invoice = i
                if withholding.fisic == True:
                    pass
                else:
                    withholding.set_number()
                invoice.write([invoice],{ 'ref_withholding': withholding.number})
            withholding.write([withholding],{'total_amount2':(withholding.total_amount*-1)})
        cls.write(withholdings, {'state': 'validated'})

    def replace_charter(self, cadena):
        reemplazo = {u"Â":"A", u"Á":"A", u"À":"A", u"Ä":"A", u"É":"E", u"È":"E", u"Ê":"E",u"Ë":"E",
            u"Í":"I",u"Ì":"I",u"Î":"I",u"Ï":"I",u"Ó":"O",u"Ò":"O",u"Ö":"O",u"Ô":"O",u"Ú":"U",u"Ù":"U",u"Ü":"U",
            u"Û":"U",u"á":"a",u"à":"a",u"â":"a",u"ä":"a",u"é":"e",u"è":"e",u"ê":"e",u"ë":"e",u"í":"i",u"ì":"i",
            u"ï":"i",u"î":"i",u"ó":"o",u"ò":"o",u"ô":"o",u"ö":"o",u"ú":"u",u"ù":"u",u"ü":"u",u"û":"u",u"ñ":"n",
            u"Ñ":"N"}
        regex = re.compile("(%s)" % "|".join(map(re.escape, reemplazo.keys())))
        nueva_cadena = regex.sub(lambda x: str(reemplazo[x.string[x.start():x.end()]]), cadena)
        return nueva_cadena

    def get_invoice_element_w(self):
        """
        """
        company = self.company
        party = self.party
        infoCompRetencion = etree.Element('infoCompRetencion')
        etree.SubElement(infoCompRetencion, 'fechaEmision').text = self.withholding_date.strftime('%d/%m/%Y')
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
        if self.party.commercial_name:
            etree.SubElement(infoCompRetencion, 'razonSocialSujetoRetenido').text = self.replace_charter(self.party.commercial_name) #self.party.commercial_name
        else:
            etree.SubElement(infoCompRetencion, 'razonSocialSujetoRetenido').text = self.replace_charter(self.party.name) #self.party.name
        etree.SubElement(infoCompRetencion, 'identificacionSujetoRetenido').text = self.party.vat_number
        etree.SubElement(infoCompRetencion, 'periodoFiscal').text = self.move.period.start_date.strftime('%m/%Y')
        return infoCompRetencion

    def get_tax_element(self):
        company = self.company
        number = self.number
        #auth = self.journal_id.auth_id
        infoTributaria = etree.Element('infoTributaria')
        etree.SubElement(infoTributaria, 'ambiente').text = '1'
        #proxy.SriService.get_active_env()
        etree.SubElement(infoTributaria, 'tipoEmision').text = self.company.emission_code
        etree.SubElement(infoTributaria, 'razonSocial').text = self.replace_charter(self.company.party.name) #self.company.party.name
        if self.company.party.commercial_name:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.replace_charter(self.company.party.commercial_name) #self.company.party.commercial_name
        etree.SubElement(infoTributaria, 'ruc').text = self.company.party.vat_number
        etree.SubElement(infoTributaria, 'claveAcceso').text = self.generate_access_key()
        etree.SubElement(infoTributaria, 'codDoc').text = tipoDocumento[self.type]
        etree.SubElement(infoTributaria, 'estab').text = number[0:3]
        etree.SubElement(infoTributaria, 'ptoEmi').text = number[4:7]
        etree.SubElement(infoTributaria, 'secuencial').text = number[8:17]
        if self.company.party.addresses:
            etree.SubElement(infoTributaria, 'dirMatriz').text = self.company.party.addresses[0].street
        return infoTributaria

    def action_generate_invoice_w(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        ACTIVE_ERROR = u"Ud. no se encuentra activo, verifique su pago. \nComuníquese con NODUX"
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
        date_f = self.withholding_date
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

            # XML del comprobante electronico: retencion
            comprobanteRetencion1 = self.generate_xml_invoice_w()
            #validacion del xml (llama metodo validate xml de sri)
            comprobanteRetencion = etree.tostring(comprobanteRetencion1, encoding = 'utf8', method = 'xml')
            a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(comprobanteRetencion, 'in_withholding', {})
            if a:
                self.raise_user_error(a)

            file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
            file_check = (nuevaruta+'/'+name_c)
            password = self.company.password_pk12
            error = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
            if error == '1':
                self.raise_user_error('No se ha encontrado el archivo de firma digital (.p12)')

            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(comprobanteRetencion, file_pk12, password,{})

            #envio al sri para recepcion del comprobante electronico
            result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
            if result != True:
                self.raise_user_error(result)
            #s.model.nodux_electronic_invoice_auth.conexionescount_voucher('in_withholding', {})
            time.sleep(WAIT_FOR_RECEIPT)
            # solicitud al SRI para autorizacion del comprobante electronico
            doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_r, 'in_withholding', signed_document, {})

            if doc_xml is None:
                msg = ' '.join(m)
                raise m

            if auth == 'NO AUTORIZADO':
                self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
                #self.raise_user_error(m)
            else:
                pass

            self.send_mail_invoice(doc_xml, access_key, send_m, s)

            return access_key

    #obtener impuestos (plan de cuentas, impuestos)
    #cuando los impuestos sean negativos multiplicar rate*-100 y tax.amount*-1
    def get_taxes(self):
        impuestos = etree.Element('impuestos')
        for tax in self.taxes:
            """
            fecha = str(self.ambiente).replace('-','/')
            m = fecha[8:10]
            d = fecha[5:7]
            y = fecha[0:4]
            """
            print "tax.tax.code_withholding ***", tax.tax
            impuesto = etree.Element('impuesto')
            if tax.tax.code_withholding:
                etree.SubElement(impuesto, 'codigo').text = tax.tax.code_withholding
            else:
                self.raise_user_error('No ha configurado el impuesto asignado para la retencion \nDirijase a:Impuestos, Impuestos, Seleccione el impuesto, Codigo')
            if tax.tax.code_electronic:
                etree.SubElement(impuesto, 'codigoRetencion').text = tax.tax.code_electronic.code
            else:
                self.raise_user_error('No ha configurado el codigo de retencion \n Dirijase a: Impuestos, Impuestos, Seleccione el impuesto, Codigo')
            etree.SubElement(impuesto, 'baseImponible').text = '{:.2f}'.format(tax.base)
            etree.SubElement(impuesto, 'porcentajeRetener').text= '{:.0f}'.format(tax.tax.rate*(-100))
            etree.SubElement(impuesto, 'valorRetenido').text= '{:.2f}'.format(tax.amount*(-1))
            etree.SubElement(impuesto, 'codDocSustento').text="01"
            etree.SubElement(impuesto, 'numDocSustento').text=(self.number_w).replace('-','')
            etree.SubElement(impuesto, 'fechaEmisionDocSustento').text= self.withholding_date.strftime('%d/%m/%Y')
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

    def generate_access_key(self):
        f = self.withholding_date.strftime('%d%m%Y')
        t_cbte = tipoDocumento[self.type]
        ruc = self.company.party.vat_number
        #t_amb=proxy.SriService.get_active_env()
        t_amb="1"
        n_cbte= self.number
        cod= "13245768"
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
        fecha = str(self.withholding_date)
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

    def elimina_tildes(self,s):
        return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))


    def send_mail_invoice(self, xml_element, access_key, send_m, s, server="localhost"):
        MAIL= u"Ud no ha configurado el correo del cliente. Diríjase a: \nTerceros->General->Medios de Contacto"
        pool = Pool()
        empresa = self.replace_charter(self.company.party.name) #self.elimina_tildes(self.company.party.name)
        empresa = empresa.replace(' ','_')
        empresa = empresa.lower()

        ahora = datetime.datetime.now()
        year = str(ahora.year)
        client = self.replace_charter(self.party.name) #self.party.name
        client = client.upper()
        empresa_ = self.company.party.name
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
        InvoiceReport = Pool().get('account.withholding.print_withholding_e', type='report')
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

class PrintWithholdingE(CompanyReport):
    'Print Withholding E'
    __name__ = 'account.withholding.print_withholding_e'

    @classmethod
    def __setup__(cls):
        super(PrintWithholdingE, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        Withholding = Pool().get('account.withholding')

        res = super(PrintWithholdingE, cls).execute(ids, data)
        if len(ids) > 1:
            res = (res[0], res[1], True, res[3])
        else:
            invoice = Withholding(ids[0])
            if invoice.number:
                res = (res[0], res[1], res[2], res[3] + ' - ' + invoice.number)
        return res

    @classmethod
    def _get_records(cls, ids, model, data):
        with Transaction().set_context(language=False):
            return super(PrintWithholdingE, cls)._get_records(ids[:1], model, data)

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        Withholding = pool.get('account.invoice')

        withholding = records[0]
        localcontext['company'] = Transaction().context.get('company')
        localcontext['barcode_img']=cls._get_barcode_img(Withholding, withholding)
        #localcontext['invoice'] = Transaction().context.get('invoice')
        return super(PrintWithholdingE, cls).parse(report,
                records, data, localcontext)

    @classmethod
    def _get_barcode_img(cls, Withholding, withholding):
        from barras import CodigoBarra
        from cStringIO import StringIO as StringIO
        # create the helper:
        codigobarra = CodigoBarra()
        output = StringIO()
        bars= withholding.numero_autorizacion
        codigobarra.GenerarImagen(bars, output, basewidth=3, width=380, height=50, extension="PNG")
        image = buffer(output.getvalue())
        output.close()
        return image
