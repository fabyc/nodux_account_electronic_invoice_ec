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

import collections
import logging
from decimal import Decimal
from OpenSSL.crypto import *
import base64
import datetime
from trytond.pyson import Eval
from trytond.pyson import Id
from trytond.modules.company import CompanyReport
from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool, PoolMeta
from lxml import etree
from xml.dom.minidom import parse, parseString
from socket import error as SocketError
import xml.etree.cElementTree as ET
import time
#from trytond.modules.electronic.conexiones import SriService, DocumentXML
#from trytond.modules.electronic.xadesBes import Xades
import code128
import xmlrpclib
import shutil
import os.path
import unicodedata
from trytond.rpc import RPC
import re

PASSWORD = 'pruebasfacturacion'
USER = "admin"
s = xmlrpclib.ServerProxy ('http://%s:%s@192.168.1.45:7069/pruebasfacturacion' % (USER, PASSWORD))

#try:
#    from suds.client import Client
#    from suds.transport import TransportError
#except ImportError:
#    raise ImportError('Instalar Libreria suds')


__all__ = ['ShipmentOut','SendSriLoteStartShipment', 'SendSriLoteShipment',
'PrintShipmentE', 'ShipmentInternal','SendSriLoteStartShipmentInternal',
'SendSriLoteShipmentInternal', 'PrintShipmentInternalE']

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

class ShipmentOut():
    "Customer Shipment"
    __name__ = 'stock.shipment.out'

    remision = fields.Boolean(u'Enviar Guía de Remisión al SRI', states={
        'readonly': Eval('state') == 'done',
    })
    placa = fields.Char('Placa del medio de Transporte', states={
        'invisible':~Eval('remision',False),
        'required': Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    cod_estab_destino = fields.Char(u'Código de establecimiento de Destino', size=3, states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })
    ruta = fields.Char('Ruta', states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    partida = fields.Char('Direccion de partida', states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    estado_sri= fields.Char(u'Estado Comprobante-Electrónico', size=24, readonly=True, states={
        'invisible':~Eval('remision',False),
        'required': Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })
    number_c= fields.Char(u'Número del Documento de Sustento', size=17, states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })
    path_xml = fields.Char(u'Path archivo xml de comprobante', readonly=True)
    path_pdf = fields.Char(u'Path archivo pdf de factura', readonly=True)
    numero_autorizacion = fields.Char(u'Número de Autorización', readonly= True)
    transporte = fields.Many2One('carrier','Transportista',states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        cls.effective_date.states['required'] = Eval('remision', True)
        cls.planned_date.states['required'] = Eval('remision', True)

    @classmethod
    def default_remision(cls):
        return True

    @fields.depends('moves', 'remision', 'number_c')
    def on_change_remision(self):
        res = {}
        venta = None
        invoices = None
        invoice = None
        if self.remision == True:
            for s in self.moves:
                venta = s.sale
            pool = Pool()
            Invoice = pool.get('account.invoice')
            invoices = Invoice.search([('description', '=', venta.reference)])
            if invoices:
                for i in invoices:
                    invoice = i
            if invoice:
                res['number_c'] = invoice.number
            else:
                res['number_c'] = None
        return res

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        pool = Pool()
        Move = pool.get('stock.move')
        Date = pool.get('ir.date')
        lote_remission = True
        Configuration = pool.get('account.configuration')
        if Configuration(1).lote_remission != None:
            lote_remission = Configuration(1).lote_remission

        for shipment in shipments:
            if shipment.remision == True and lote_remission == False:
                shipment.get_tax_element()
                shipment.get_shipment_element()
                shipment.get_destinatarios()
                shipment.generate_xml_shipment()
                shipment.action_generate_shipment()
                shipment.connect_db()
        Move.do([m for s in shipments for m in s.outgoing_moves])
        cls.write([s for s in shipments if not s.effective_date], {
                'effective_date': Date.today(),
                })

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
        nombre = self.customer.name
        cedula = self.customer.vat_number
        ruc = self.company.party.vat_number
        nombre_e = self.company.party.name
        tipo = 'out_shipment'
        fecha = str(self.effective_date)
        empresa = self.company.party.name
        numero = self.code
        path_xml = self.path_xml
        path_pdf = self.path_pdf
        estado = self.estado_sri
        auth = self.numero_autorizacion
        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        for c in correo:
            if c.party == self.customer:
                to_email = c.value
            if c.party == self.company.party:
                to_email_2 = c.value
        email_e= to_email_2
        email = to_email
        total = ''
        if self.estado_sri == 'AUTORIZADO':
            s.model.nodux_electronic_invoice_auth.conexiones.connect_db( nombre, cedula, ruc, nombre_e, tipo, fecha, empresa, numero, path_xml, path_pdf,estado, auth, email, email_e, total, {})

    def send_mail_invoice(self, xml_element, access_key, send_m, s, server="localhost"):
        MAIL= u"Ud no ha configurado el correo del cliente. Diríjase a: \nTerceros->General->Medios de Contacto"
        pool = Pool()
        empresa = self.elimina_tildes(self.company.party.name)
        #empresa = unicode(empresa, 'utf-8')
        empresa = str(self.elimina_tildes(empresa))
        empresa = empresa.replace(' ','_')
        empresa = empresa.lower()

        ahora = datetime.datetime.now()
        year = str(ahora.year)
        client = self.customer.name
        client = client.upper()
        empresa_ = self.company.party.name
        ruc = self.company.party.vat_number

        if ahora.month < 10:
            month = '0'+ str(ahora.month)
        else:
            month = str(ahora.month)
        tipo = 'rem_'
        n_tipo = "GUIA DE REMISION"

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
        self.write([self],{'path_xml': new_save+name_xml,'numero_autorizacion' : access_key, 'path_pdf':new_save+name_pdf})

        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        InvoiceReport = Pool().get('stock.shipment.out.print_shipment_e', type='report')
        report = InvoiceReport.execute([self.id], {})

        email=''
        cont = 0
        for c in correo:
            if c.party == self.customer:
                email = c.value
            if c.party == self.company.party:
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

    def elimina_tildes(self,s):
        return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

    def generate_access_key(self):
        fecha = self.create_date.strftime('%d%m%Y')
        tipo_cbte = '06'
        ruc = self.company.party.vat_number
        tipo_amb=self.company.tipo_de_ambiente
        num_cbte= self.code
        cod_num= "13245768"
        tipo_emision= self.company.emission_code
        numero_cbte= num_cbte.replace('-','')
        #unimos todos los datos en una sola cadena
        clave_inicial=fecha + tipo_cbte + ruc + tipo_amb + numero_cbte + cod_num + tipo_emision
        #recorremos la cadena para ir guardando en una lista de enteros
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
        clave_acceso= clave_inicial+digito
        return clave_acceso

    def generate_access_key_lote(self):
        fecha = self.create_date.strftime('%d%m%Y')
        tipo_cbte = '06'
        ruc = self.company.party.vat_number
        tipo_amb=self.company.tipo_de_ambiente
        n_cbte= self.code
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

    def get_tax_element(self):

        company = self.company
        number = self.code
        #auth = self.journal_id.auth_id
        infoTributaria = etree.Element('infoTributaria')
        etree.SubElement(infoTributaria, 'ambiente').text = self.company.tipo_de_ambiente
        #SriService.get_active_env()

        etree.SubElement(infoTributaria, 'tipoEmision').text = self.company.emission_code
        etree.SubElement(infoTributaria, 'razonSocial').text = self.company.party.name
        if self.company.party.commercial_name:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.commercial_name
        else:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.name
        etree.SubElement(infoTributaria, 'ruc').text = self.company.party.vat_number
        etree.SubElement(infoTributaria, 'claveAcceso').text = self.generate_access_key()
        etree.SubElement(infoTributaria, 'codDoc').text = "06"
        etree.SubElement(infoTributaria, 'estab').text = number[0:3]
        etree.SubElement(infoTributaria, 'ptoEmi').text = number[4:7]
        etree.SubElement(infoTributaria, 'secuencial').text = number[8:17]
        if self.company.party.addresses:
            etree.SubElement(infoTributaria, 'dirMatriz').text = self.company.party.addresses[0].street
        return infoTributaria

    def get_shipment_element(self):

        company =  self.company
        customer = self.customer
        infoGuiaRemision = etree.Element('infoGuiaRemision')
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirEstablecimiento').text = self.company.party.addresses[0].street
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirPartida').text = self.partida
        etree.SubElement(infoGuiaRemision, 'razonSocialTransportista').text= self.transporte.party.name
        etree.SubElement(infoGuiaRemision, 'tipoIdentificacionTransportista').text= tipoIdentificacion[self.transporte.party.type_document]
        etree.SubElement(infoGuiaRemision, 'rucTransportista').text= self.transporte.party.vat_number
        etree.SubElement(infoGuiaRemision, 'rise').text= "No  obligatorios"
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoGuiaRemision, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoGuiaRemision, 'obligadoContabilidad').text = 'NO'

        if self.company.party.contribuyente_especial_nro:
            etree.SubElement(infoGuiaRemision, 'contribuyenteEspecial').text = self.company.party.contribuyente_especial_nro
        etree.SubElement(infoGuiaRemision, 'fechaIniTransporte').text= self.planned_date.strftime('%d/%m/%Y')
        etree.SubElement(infoGuiaRemision, 'fechaFinTransporte').text= self.planned_date.strftime('%d/%m/%Y')
        etree.SubElement(infoGuiaRemision, 'placa').text= self.placa
        return infoGuiaRemision

    def get_destinatarios(self):
        ERROR= u"No existe factura registrada con el número que ingresó"
        num_mod=self.number_c
        pool = Pool()
        Invoices = pool.get('account.invoice')
        invoice = Invoices.search([('number','=',num_mod)])
        if invoice:
            pass
        else:
            self.raise_user_error(ERROR)
        for i in invoice:
            date_mod = i.invoice_date.strftime('%d/%m/%Y')
            num_aut = i.numero_autorizacion

        company =  self.company
        customer = self.customer
        destinatarios=etree.Element('destinatarios')
        destinatario= etree.Element('destinatario')
        etree.SubElement(destinatario, 'identificacionDestinatario').text = self.customer.vat_number
        etree.SubElement(destinatario, 'razonSocialDestinatario').text = self.customer.name
        etree.SubElement(destinatario, 'dirDestinatario').text = self.dir_destinatario
        etree.SubElement(destinatario, 'motivoTraslado').text = self.motivo_traslado
        etree.SubElement(destinatario, 'docAduaneroUnico').text = " "
        etree.SubElement(destinatario, 'codEstabDestino').text = self.cod_estab_destino
        etree.SubElement(destinatario, 'ruta').text = self.ruta
        etree.SubElement(destinatario, 'codDocSustento').text = "01"
        etree.SubElement(destinatario, 'numDocSustento').text = num_mod
        if num_aut:
            #etree.SubElement(destinatario, 'numAutDocSustento').text = num_aut
            print "Si hay autorizacion"
        etree.SubElement(destinatario, 'fechaEmisionDocSustento').text = date_mod#self.create_date.strftime('%d/%m/%Y')

        detalles = etree.Element('detalles')
        def fix_chars(code):
            if code:
                code.replace(u'%',' ').replace(u'º', ' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                return code
            return '1'
        detalle = etree.Element('detalle')
        for move in self.moves:
            move = move
        etree.SubElement(detalle, 'codigoInterno').text = fix_chars(move.product.code)
        etree.SubElement(detalle, 'descripcion').text = fix_chars(move.product.name)
        etree.SubElement(detalle, 'cantidad').text = str(move.quantity)
        detalles.append(detalle)
        destinatario.append(detalles)
        destinatarios.append(destinatario)
        return destinatarios

    def generate_xml_shipment(self):
        guiaRemision = etree.Element('guiaRemision')
        guiaRemision.set("id", "comprobante")
        guiaRemision.set("version", "1.1.0")

        #generar infoTributaria
        infoTributaria = self.get_tax_element()
        guiaRemision.append(infoTributaria)

        #generar infoGuiaRemision
        infoGuiaRemision = self.get_shipment_element()
        guiaRemision.append(infoGuiaRemision)

        #generar destinatarios
        destinatarios= self.get_destinatarios()
        guiaRemision.append(destinatarios)

        return guiaRemision

    def check_before_sent(self):

        sql = "select autorizado_sri, number from account_invoice where state='open' and number < '%s' order by number desc limit 1" % self.number
        self.execute(sql)
        res = self.fetchone()
        return res[0] and True or False

    def action_generate_shipment(self):

        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        ACTIVE_ERROR = u"Ud. no se encuentra activo, verifique su pago. \nComuníquese con NODUX"
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben \nser enviados al SRI, en un plazo máximo de 24 horas'

        #Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.effective_date
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

        name = self.company.party.name
        name_l=name.lower()
        name_r = name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
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

        guiaRemision1 = self.generate_xml_shipment()
        guiaRemision = etree.tostring(guiaRemision1, encoding = 'utf8', method='xml')
        #validacion del xml (llama metodo validate xml de sri)
        a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(guiaRemision, 'out_shipment', {})
        if a:
                self.raise_user_error(a)
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        file_check = (nuevaruta+'/'+name_c)
        password = self.company.password_pk12
        error = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
        if error == '1':
            self.raise_user_error('No se ha encontrado el archivo de firma digital (.p12)')

        signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(guiaRemision, file_pk12, password,{})

        #envio al sri para recepcion del comprobante electronico
        result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
        if result != True:
            self.raise_user_error(result)
        time.sleep(WAIT_FOR_RECEIPT)
        # solicitud al SRI para autorizacion del comprobante electronico
        doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_r, 'out_shipment', signed_document, {})
        if doc_xml is None:
            msg = ' '.join(m)
            raise m

        if auth == 'NO AUTORIZADO':
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO', 'mensaje':doc_xml})

        else:
            self.write([self],{ 'estado_sri': 'AUTORIZADO'})
            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        return access_key

    def action_generate_lote_shipment(self):

        LIMIT_TO_SEND = 5
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electronicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Los comprobantes electronicos deben ser enviados al SRI para su autorizacion, en un plazo maximo de 24 horas'

        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        name = self.company.party.name
        name_l=name.lower()
        name_l=name_l.replace(' ','_')
        name_r = self.replace_character(name_l)
        name_c = name_r+'.p12'

        access_key = self.generate_access_key_lote()
        lote1 = self.generate_xml_lote_shipment()
        lote = etree.tostring(lote1, encoding = 'utf8', method ='xml')

        authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})

        a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(lote, 'lote', {})
        if a:
            self.raise_user_error(a)

        result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(lote, {})
        if result != True:
            self.raise_user_error(result)
        time.sleep(WAIT_FOR_RECEIPT)
        # solicitud al SRI para autorizacion del comprobante electronico
        doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization_lote(access_key, name_l, 'lote_out_shipment',{})

        if doc_xml is None:
            msg = ' '.join(m)
            raise m

        if auth == 'NO AUTORIZADO':
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO', 'mensaje':doc_xml})

        else:
            self.write([self],{ 'estado_sri': 'AUTORIZADO'})
            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        return access_key


    def generate_xml_lote_shipment(self):
        pool = Pool()
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)
        name = self.company.party.name
        name_r = name.replace(' ','_')
        name_l=name_r.lower()
        name_c = name_l+'.p12'

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
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        password = base64.encodestring(self.company.password_pk12)

        Shipment = Pool().get('stock.shipment.out')
        shipments = Shipment.browse(Transaction().context['active_ids'])

        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for shipment in shipments:
            guiaRemision1 = shipment.generate_xml_shipment()
            guiaRemision = etree.tostring(guiaRemision1, encoding='utf-8', method='xml')
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(guiaRemision, file_pk12, password,{})
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote

class SendSriLoteStartShipment(ModelView):
    'Send Sri Lote Start'
    __name__ = 'nodux.account.electronic.invoice.ec.lote.shipment.start'


class SendSriLoteShipment(Wizard):
    'Send Sri Lote'
    __name__ = 'nodux.account.electronic.invoice.ec.lote.shipment'

    start = StateView('nodux.account.electronic.invoice.ec.lote.shipment.start',
        'nodux_account_electronic_invoice_ec.send_sri_lote_shipment_start_view_form', [
        Button('Cancel', 'end', 'tryton-cancel'),
        Button('Ok', 'accept', 'tryton-ok', default=True),
        ])
    accept = StateTransition()

    def transition_accept(self):
        Shipment = Pool().get('stock.shipment.out')
        shipments = Shipment.browse(Transaction().context['active_ids'])
        for shipment in shipments:
            if shipment.estado_sri == 'AUTORIZADO':
                self.raise_user_error('Factura ya ha sido autorizada')
                return 'end'
            else:
                shipment.generate_xml_lote_shipment()
                shipment.action_generate_lote_shipment()
        return 'end'

class PrintShipmentE(CompanyReport):
    'Print Shipment E'
    __name__ = 'stock.shipment.out.print_shipment_e'

    @classmethod
    def __setup__(cls):
        super(PrintShipmentE, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        Shipment = Pool().get('stock.shipment.out')

        res = super(PrintShipmentE, cls).execute(ids, data)
        if len(ids) > 1:
            res = (res[0], res[1], True, res[3])
        else:
            invoice = Shipment(ids[0])
            if invoice.code:
                res = (res[0], res[1], res[2], res[3] + ' - ' + invoice.code)
        return res

    @classmethod
    def _get_records(cls, ids, model, data):
        with Transaction().set_context(language=False):
            return super(PrintShipmentE, cls)._get_records(ids[:1], model, data)

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')
        shipment = records[0]

        num_mod=shipment.number_c
        pool = Pool()
        Invoices = pool.get('account.invoice')
        invoices = Invoices.search([('number','=',num_mod)])
        if invoices:
            for i in invoices:
                invoice = i
        if invoice:
            localcontext['invoice'] = invoice
        localcontext['company'] = Transaction().context.get('company')
        if shipment.numero_autorizacion:
            localcontext['barcode_img']= cls._get_barcode_img(Shipment, shipment)
        else:
            pass
        #localcontext['invoice'] = Transaction().context.get('invoice')
        return super(PrintShipmentE, cls).parse(report, records, data, localcontext)

    @classmethod
    def _get_barcode_img(cls, Shipment, shipment):
        from barras import CodigoBarra
        from cStringIO import StringIO as StringIO
        # create the helper:
        codigobarra = CodigoBarra()
        output = StringIO()
        bars= shipment.numero_autorizacion
        codigobarra.GenerarImagen(bars, output, basewidth=3, width=380, height=50, extension="PNG")
        image = buffer(output.getvalue())
        output.close()
        return image

class ShipmentInternal():
    "Internal Shipment"
    __name__ = 'stock.shipment.internal'

    remision = fields.Boolean(u'Enviar Guía de Remisión al SRI', states={
        'readonly': Eval('state') == 'done',
    })
    placa = fields.Char('Placa del medio de Transporte', states={
        'invisible':~Eval('remision',False),
        'required': Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    cod_estab_destino = fields.Char(u'Código de establecimiento de Destino', size=3, states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })
    ruta = fields.Char('Ruta', states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    partida = fields.Char('Direccion de partida', states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision',True),
        'readonly': Eval('state') == 'done',
    })
    estado_sri= fields.Char(u'Estado Comprobante-Electrónico', size=24, readonly=True, states={
        'invisible':~Eval('remision',False),
        'readonly': Eval('state') == 'done',
    })
    number_c= fields.Char(u'Número del Documento de Sustento', size=17, states={
        'invisible':~Eval('remision',False),
        'readonly': Eval('state') == 'done',
    })
    path_xml = fields.Char(u'Path archivo xml de comprobante', readonly=True)
    path_pdf = fields.Char(u'Path archivo pdf de factura', readonly=True)
    numero_autorizacion = fields.Char(u'Número de Autorización', readonly= True)
    transporte = fields.Many2One('carrier','Transportista',states={
        'invisible':~Eval('remision',False),
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })

    motivo_traslado = fields.Char('Motivo de Traslado', states={
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })
    dir_destinatario = fields.Char(u'Dirección de LLegada de Productos', states={
        'required' : Eval('remision', True),
        'readonly': Eval('state') == 'done',
    })


    @classmethod
    def __setup__(cls):
        super(ShipmentInternal, cls).__setup__()
        cls.effective_date.states['required'] = Eval('remision', True)
        cls.planned_date.states['required'] = Eval('remision', True)

    @classmethod
    def default_remision(cls):
        return True

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        pool = Pool()
        Move = pool.get('stock.move')
        Date = pool.get('ir.date')
        lote_remission = True
        Configuration = pool.get('account.configuration')
        if Configuration(1).lote_remission != None:
            lote_remission = Configuration(1).lote_remission

        for shipment in shipments:
            if shipment.remision == True and lote_remission == False:
                shipment.get_tax_element()
                shipment.get_shipment_element()
                shipment.get_destinatarios()
                shipment.generate_xml_shipment()
                shipment.action_generate_shipment()
                shipment.connect_db()

        Move.do([m for s in shipments for m in s.moves])
        cls.write([s for s in shipments if not s.effective_date], {
                'effective_date': Date.today(),
                })

    def replace_character(self, cadena):
        reemplazo = {u"Â":"A", u"Á":"A", u"À":"A", u"Ä":"A", u"É":"E", u"È":"E", u"Ê":"E",u"Ë":"E",
            u"Í":"I",u"Ì":"I",u"Î":"I",u"Ï":"I",u"Ó":"O",u"Ò":"O",u"Ö":"O",u"Ô":"O",u"Ú":"U",u"Ù":"U",u"Ü":"U",
            u"Û":"U",u"á":"a",u"à":"a",u"â":"a",u"ä":"a",u"é":"e",u"è":"e",u"ê":"e",u"ë":"e",u"í":"i",u"ì":"i",
            u"ï":"i",u"î":"i",u"ó":"o",u"ò":"o",u"ô":"o",u"ö":"o",u"ú":"u",u"ù":"u",u"ü":"u",u"û":"u",u"ñ":"n",
            u"Ñ":"N", u"Nº":"No", u"nº":"No"}
        regex = re.compile("(%s)" % "|".join(map(re.escape, reemplazo.keys())))
        nueva_cadena = regex.sub(lambda x: str(reemplazo[x.string[x.start():x.end()]]), cadena)
        return nueva_cadena

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
        nombre = self.company.party.name
        cedula = self.company.party.vat_number
        ruc = self.company.party.vat_number
        nombre_e = self.company.party.name
        tipo = 'out_shipment'
        fecha = str(self.effective_date)
        empresa = self.company.party.name
        numero = self.code
        path_xml = self.path_xml
        path_pdf = self.path_pdf
        estado = self.estado_sri
        auth = self.numero_autorizacion
        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        for c in correo:
            if c.party == self.company.party:
                to_email = c.value
            if c.party == self.company.party:
                to_email_2 = c.value
        email_e= to_email_2
        email = to_email
        total = ''
        if self.estado_sri == 'AUTORIZADO':
            s.model.nodux_electronic_invoice_auth.conexiones.connect_db( nombre, cedula, ruc, nombre_e, tipo, fecha, empresa, numero, path_xml, path_pdf,estado, auth, email, email_e, total, {})

    def send_mail_invoice(self, xml_element, access_key, send_m, s, server="localhost"):
        MAIL= u"Ud no ha configurado el correo del cliente. Diríjase a: \nTerceros->General->Medios de Contacto"
        pool = Pool()
        empresa = self.elimina_tildes(self.company.party.name)
        #empresa = unicode(empresa, 'utf-8')
        empresa = str(self.elimina_tildes(empresa))
        empresa = empresa.replace(' ','_')
        empresa = empresa.lower()

        ahora = datetime.datetime.now()
        year = str(ahora.year)
        client = self.company.party.name
        client = client.upper()
        empresa_ = self.company.party.name
        ruc = self.company.party.vat_number

        if ahora.month < 10:
            month = '0'+ str(ahora.month)
        else:
            month = str(ahora.month)
        tipo = 'rem_'
        n_tipo = "GUIA DE REMISION"

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
        self.write([self],{'path_xml': new_save+name_xml,'numero_autorizacion' : access_key, 'path_pdf':new_save+name_pdf})

        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        InvoiceReport = Pool().get('stock.shipment.internal.print_shipment_internal_e', type='report')
        report = InvoiceReport.execute([self.id], {})

        email=''
        cont = 0
        for c in correo:
            if c.party == self.company.party:
                email = c.value
            if c.party == self.company.party:
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

    def elimina_tildes(self,s):
        return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

    def generate_access_key(self):
        fecha = self.effective_date.strftime('%d%m%Y')
        tipo_cbte = '06'
        ruc = self.company.party.vat_number
        tipo_amb=self.company.tipo_de_ambiente
        num_cbte= self.code
        cod_num= "13245768"
        tipo_emision= self.company.emission_code
        numero_cbte= num_cbte.replace('-','')
        #unimos todos los datos en una sola cadena
        clave_inicial=fecha + tipo_cbte + ruc + tipo_amb + numero_cbte + cod_num + tipo_emision
        #recorremos la cadena para ir guardando en una lista de enteros
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
        clave_acceso= clave_inicial+digito
        return clave_acceso

    def generate_access_key_lote(self):
        fecha = time.strftime('%d%m%Y')
        tipo_cbte = '06'
        ruc = self.company.party.vat_number
        tipo_amb=self.company.tipo_de_ambiente
        n_cbte= self.code
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

    def get_tax_element(self):

        company = self.company
        number = self.code
        #auth = self.journal_id.auth_id
        infoTributaria = etree.Element('infoTributaria')
        etree.SubElement(infoTributaria, 'ambiente').text = self.company.tipo_de_ambiente
        #SriService.get_active_env()

        etree.SubElement(infoTributaria, 'tipoEmision').text = self.company.emission_code
        etree.SubElement(infoTributaria, 'razonSocial').text = self.company.party.name
        if self.company.party.commercial_name:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.commercial_name
        else:
            etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.name
        etree.SubElement(infoTributaria, 'ruc').text = self.company.party.vat_number
        etree.SubElement(infoTributaria, 'claveAcceso').text = self.generate_access_key()
        etree.SubElement(infoTributaria, 'codDoc').text = "06"
        etree.SubElement(infoTributaria, 'estab').text = number[0:3]
        etree.SubElement(infoTributaria, 'ptoEmi').text = number[4:7]
        etree.SubElement(infoTributaria, 'secuencial').text = number[8:17]
        if self.company.party.addresses:
            etree.SubElement(infoTributaria, 'dirMatriz').text = self.company.party.addresses[0].street
        return infoTributaria

    def get_shipment_element(self):

        company =  self.company
        customer = self.company.party
        infoGuiaRemision = etree.Element('infoGuiaRemision')
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirEstablecimiento').text = self.company.party.addresses[0].street
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirPartida').text = self.partida
        etree.SubElement(infoGuiaRemision, 'razonSocialTransportista').text= self.transporte.party.name
        etree.SubElement(infoGuiaRemision, 'tipoIdentificacionTransportista').text= tipoIdentificacion[self.transporte.party.type_document]
        etree.SubElement(infoGuiaRemision, 'rucTransportista').text= self.transporte.party.vat_number
        etree.SubElement(infoGuiaRemision, 'rise').text= "No  obligatorios"
        if self.company.party.mandatory_accounting:
            etree.SubElement(infoGuiaRemision, 'obligadoContabilidad').text = self.company.party.mandatory_accounting
        else :
            etree.SubElement(infoGuiaRemision, 'obligadoContabilidad').text = 'NO'

        if self.company.party.contribuyente_especial_nro:
            etree.SubElement(infoGuiaRemision, 'contribuyenteEspecial').text = self.company.party.contribuyente_especial_nro
        etree.SubElement(infoGuiaRemision, 'fechaIniTransporte').text= self.planned_date.strftime('%d/%m/%Y')
        etree.SubElement(infoGuiaRemision, 'fechaFinTransporte').text= self.planned_date.strftime('%d/%m/%Y')
        etree.SubElement(infoGuiaRemision, 'placa').text= self.placa
        return infoGuiaRemision

    def get_destinatarios(self):
        """
        ERROR= u"No existe factura registrada con el número que ingresó"
        num_mod=self.number_c
        pool = Pool()
        Invoices = pool.get('account.invoice')
        invoice = Invoices.search([('number','=',num_mod)])
        if invoice:
            pass
        else:
            self.raise_user_error(ERROR)
        for i in invoice:
            date_mod = i.invoice_date.strftime('%d/%m/%Y')
            num_aut = i.numero_autorizacion
        """
        company =  self.company
        customer = self.company
        destinatarios=etree.Element('destinatarios')
        destinatario= etree.Element('destinatario')
        etree.SubElement(destinatario, 'identificacionDestinatario').text = self.company.party.vat_number
        etree.SubElement(destinatario, 'razonSocialDestinatario').text = self.company.party.name
        etree.SubElement(destinatario, 'dirDestinatario').text = self.dir_destinatario
        etree.SubElement(destinatario, 'motivoTraslado').text = self.motivo_traslado
        etree.SubElement(destinatario, 'docAduaneroUnico').text = " "
        etree.SubElement(destinatario, 'codEstabDestino').text = self.cod_estab_destino
        etree.SubElement(destinatario, 'ruta').text = self.ruta
        """
        etree.SubElement(destinatario, 'codDocSustento').text = "01"
        etree.SubElement(destinatario, 'numDocSustento').text = num_mod
        if num_aut:
            #etree.SubElement(destinatario, 'numAutDocSustento').text = num_aut
            print "Si hay autorizacion"
        etree.SubElement(destinatario, 'fechaEmisionDocSustento').text = date_mod#self.create_date.strftime('%d/%m/%Y')
        """
        detalles = etree.Element('detalles')
        def fix_chars(code):
            if code:
                code.replace(u'%',' ').replace(u'º', ' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                return code
            return '1'
        detalle = etree.Element('detalle')
        for move in self.moves:
            move = move
        etree.SubElement(detalle, 'codigoInterno').text = fix_chars(move.product.code)
        etree.SubElement(detalle, 'descripcion').text = fix_chars(move.product.name)
        etree.SubElement(detalle, 'cantidad').text = str(move.quantity)
        detalles.append(detalle)
        destinatario.append(detalles)
        destinatarios.append(destinatario)
        return destinatarios

    def generate_xml_shipment(self):
        guiaRemision = etree.Element('guiaRemision')
        guiaRemision.set("id", "comprobante")
        guiaRemision.set("version", "1.1.0")

        #generar infoTributaria
        infoTributaria = self.get_tax_element()
        guiaRemision.append(infoTributaria)

        #generar infoGuiaRemision
        infoGuiaRemision = self.get_shipment_element()
        guiaRemision.append(infoGuiaRemision)

        #generar destinatarios
        destinatarios= self.get_destinatarios()
        guiaRemision.append(destinatarios)

        return guiaRemision

    def check_before_sent(self):

        sql = "select autorizado_sri, number from account_invoice where state='open' and number < '%s' order by number desc limit 1" % self.number
        self.execute(sql)
        res = self.fetchone()
        return res[0] and True or False

    def action_generate_shipment(self):

        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
        ACTIVE_ERROR = u"Ud. no se encuentra activo, verifique su pago. \nComuníquese con NODUX"
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electrónicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Se ha excedido el límite de tiempo. Los comprobantes electrónicos deben \nser enviados al SRI, en un plazo máximo de 24 horas'

        #Validar que el envio del comprobante electronico se realice dentro de las 24 horas posteriores a su emision
        pool = Pool()
        Date = pool.get('ir.date')
        date_f = self.effective_date
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

        name = self.company.party.name
        name_l=name.lower()
        name_r = name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
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

        guiaRemision1 = self.generate_xml_shipment()
        guiaRemision = etree.tostring(guiaRemision1, encoding = 'utf8', method='xml')
        #validacion del xml (llama metodo validate xml de sri)
        a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(guiaRemision, 'out_shipment', {})
        if a:
                self.raise_user_error(a)
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        file_check = (nuevaruta+'/'+name_c)
        password = self.company.password_pk12
        error = s.model.nodux_electronic_invoice_auth.conexiones.check_digital_signature(file_check,{})
        if error == '1':
            self.raise_user_error('No se ha encontrado el archivo de firma digital (.p12)')

        signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(guiaRemision, file_pk12, password,{})

        #envio al sri para recepcion del comprobante electronico
        result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
        if result != True:
            self.raise_user_error(result)
        time.sleep(WAIT_FOR_RECEIPT)
        # solicitud al SRI para autorizacion del comprobante electronico
        doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_r, 'out_shipment', signed_document, {})
        if doc_xml is None:
            msg = ' '.join(m)
            raise m

        if auth == 'NO AUTORIZADO':
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO', 'mensaje':doc_xml})

        else:
            self.write([self],{ 'estado_sri': 'AUTORIZADO'})
            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        return access_key

    def action_generate_lote_shipment(self):

        LIMIT_TO_SEND = 5
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electronicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Los comprobantes electronicos deben ser enviados al SRI para su autorizacion, en un plazo maximo de 24 horas'

        usuario = self.company.user_ws
        password_u= self.company.password_ws
        access_key = self.generate_access_key()
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)

        name = self.company.party.name
        name_l=name.lower()
        name_l=name_l.replace(' ','_')
        name_r = self.replace_character(name_l)
        name_c = name_r+'.p12'

        access_key = self.generate_access_key_lote()
        lote1 = self.generate_xml_lote_shipment()
        lote = etree.tostring(lote1, encoding = 'utf8', method ='xml')

        authenticate, send_m, active = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})

        a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(lote, 'lote', {})
        if a:
            self.raise_user_error(a)

        result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(lote, {})
        if result != True:
            self.raise_user_error(result)
        time.sleep(WAIT_FOR_RECEIPT)
        # solicitud al SRI para autorizacion del comprobante electronico
        doc_xml, m, auth, path, numero, num = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization_lote(access_key, name_l, 'lote_out_shipment',{})

        if doc_xml is None:
            msg = ' '.join(m)
            raise m

        if auth == 'NO AUTORIZADO':
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO', 'mensaje':doc_xml})

        else:
            self.write([self],{ 'estado_sri': 'AUTORIZADO'})
            self.send_mail_invoice(doc_xml, access_key, send_m, s)

        return access_key

    def generate_xml_lote_shipment(self):

        pool = Pool()
        usuario = self.company.user_ws
        password_u= self.company.password_ws
        address_xml = self.web_service()
        s= xmlrpclib.ServerProxy(address_xml)
        name = self.company.party.name
        name_l = name.lower()
        name_l=name_l.replace(' ','_')
        name_r = self.replace_character(name_l) #name_l.replace(' ','_').replace(u'á','a').replace(u'é','e').replace(u'í', 'i').replace(u'ó','o').replace(u'ú','u')
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

        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        password = self.company.password_pk12

        Shipment = pool.get('stock.shipment.internal')
        shipments = Shipment.browse(Transaction().context['active_ids'])
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for shipment in shipments:
            shipment1 = shipment.generate_xml_shipment()
            shipment = etree.tostring(shipment1, encoding = 'utf8', method = 'xml')
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(shipment, file_pk12, password,{})
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        return lote


class SendSriLoteStartShipmentInternal(ModelView):
    'Send Sri Lote Start Shipment Interal'
    __name__ = 'nodux.account.electronic.invoice.ec.lote.shipment_internal.start'


class SendSriLoteShipmentInternal(Wizard):
    'Send Sri Lote Shipment Internal'
    __name__ = 'nodux.account.electronic.invoice.ec.lote.shipment_internal'

    start = StateView('nodux.account.electronic.invoice.ec.lote.shipment_internal.start',
        'nodux_account_electronic_invoice_ec.send_sri_lote_shipment_internal_start_view_form', [
        Button('Cancel', 'end', 'tryton-cancel'),
        Button('Ok', 'accept', 'tryton-ok', default=True),
        ])
    accept = StateTransition()

    def transition_accept(self):
        Shipment = Pool().get('stock.shipment.internal')
        shipments = Shipment.browse(Transaction().context['active_ids'])
        for shipment in shipments:
            if shipment.estado_sri == 'AUTORIZADO':
                self.raise_user_error('Factura ya ha sido autorizada')
                return 'end'
            else:
                shipment.generate_xml_lote_shipment()
                shipment.action_generate_lote_shipment()
        return 'end'

class PrintShipmentInternalE(CompanyReport):
    'Print Shipment Internal E'
    __name__ = 'stock.shipment.internal.print_shipment_internal_e'

    @classmethod
    def __setup__(cls):
        super(PrintShipmentInternalE, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        Shipment = Pool().get('stock.shipment.internal')

        res = super(PrintShipmentInternalE, cls).execute(ids, data)
        if len(ids) > 1:
            res = (res[0], res[1], True, res[3])
        else:
            shipment = Shipment(ids[0])
            if shipment.code:
                res = (res[0], res[1], res[2], res[3] + ' - ' + shipment.code)
        print "Res ", res
        return res

    @classmethod
    def _get_records(cls, ids, model, data):
        with Transaction().set_context(language=False):
            return super(PrintShipmentInternalE, cls)._get_records(ids[:1], model, data)

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        Shipment = pool.get('stock.shipment.internal')
        print "records ", records
        shipment = records[0]
        print "Shipment ", shipment
        num_mod=shipment.number_c
        pool = Pool()
        localcontext['company'] = Transaction().context.get('company')
        if shipment.numero_autorizacion:
            localcontext['barcode_img']= cls._get_barcode_img(Shipment, shipment)
        else:
            pass
        #localcontext['invoice'] = Transaction().context.get('invoice')
        return super(PrintShipmentInternalE, cls).parse(report, records, data, localcontext)

    @classmethod
    def _get_barcode_img(cls, Shipment, shipment):
        from barras import CodigoBarra
        from cStringIO import StringIO as StringIO
        # create the helper:
        codigobarra = CodigoBarra()
        output = StringIO()
        bars= shipment.numero_autorizacion
        codigobarra.GenerarImagen(bars, output, basewidth=3, width=380, height=50, extension="PNG")
        image = buffer(output.getvalue())
        output.close()
        return image
