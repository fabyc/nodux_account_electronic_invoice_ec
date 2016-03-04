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

from trytond.pyson import Eval
from trytond.pyson import Id

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

PASSWORD = 'pruebasfacturacion'
USER = "admin"
s = xmlrpclib.ServerProxy ('http://%s:%s@192.168.1.45:7069/pruebasfacturacion' % (USER, PASSWORD))

#try:
#    from suds.client import Client
#    from suds.transport import TransportError
#except ImportError:
#    raise ImportError('Instalar Libreria suds')
 
    
__all__ = ['ShipmentOut','SendSriLoteStartShipment', 'SendSriLoteShipment']
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
    
    remision = fields.Boolean(u'Enviar Guía de Remisión al SRI')  
    placa = fields.Char('Placa del medio de Transporte', states={
        'invisible':~Eval('remision',False),
        'required': Eval('remision',True),
    })
    cod_estab_destino = fields.Integer(u'Código de establecimiento de Destino', states={
        'invisible':~Eval('remision',False),
    })
    ruta = fields.Char('Ruta', states={
        'invisible':~Eval('remision',False),
    })
    estado_sri= fields.Char(u'Estado Comprobante-Electrónico', size=24, readonly=True, states={
        'invisible':~Eval('remision',False),
    })
    number_c= fields.Char(u'Número del Documento de Sustento', size=24, readonly=True, states={
        'invisible':~Eval('remision',False),
    })
    path_xml = fields.Char(u'Path archivo xml de comprobante', readonly=True)
    path_pdf = fields.Char(u'Path archivo pdf de factura', readonly=True)
    numero_autorizacion = fields.Char(u'Número de Autorización', readonly= True)
    transporte = fields.Many2One('carrier','Transportista',states={
        'invisible':~Eval('remision',False),
    })
    
    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
 
    
    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, shipments):
        pool = Pool()
        Move = pool.get('stock.move')
        Date = pool.get('ir.date')
        
        for shipment in shipments:
            if shipment.remision == True:
                print "Llega metodo"
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
                address = c.cabecera+"://"+c.usuario+":"+c.pass_db+"@"+c.direccion+":"+c.puerto+"/"+c.name_db
                return address
        else:
            self.raise_user_error(CONEXION)
     
    def connect_db(self):
        pool = Pool()
        nombre = self.customer.party.name
        cedula = self.customer.party.vat_number
        ruc = self.company.party.vat_number
        nombre_e = self.company.party.name
        tipo = self.type
        fecha = self.effective_date
        empresa = self.company.party.name
        numero = self.number
        path_xml = self.path_xml
        path_pdf = self.path_pdf
        estado = self.estado_sri
        auth = self.numero_autorizacion
        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        for c in correo:
            if c.party == self.customer.party:
                to_email = c.value
            if c.party == self.company.party:
                to_email_2 = c.value
        email_e= to_email_2
        email = to_email
        total = self.total_amount
        conn = psycopg2.connect("dbname=usuarios_web")
        cur = conn.cursor()
        admin = 'admin'+self.company.party.vat_number

        #db = create_engine('postgress:///database.sqlite', echo=False)
        #metadata.create_all(db)
        
        #bd = MySQLdb.connect("localhost","root","noduxroot","usuarios" )
        # Preparamos el cursor que nos va a ayudar a realizar las operaciones con la base de datos
        #cursor = bd.cursor()
        
        cur.execute("SELECT * FROM user_id_seq;")
        sequence = cur.fetchone()
        print sequence
        if sequence:
            print "Ya existe no se ha creado"
            pass
        else:
            print "Tambien sta entrando"
            cur.execute("CREATE SEQUENCE user_id_seq;")
            
        cur.execute("CREATE TABLE IF NOT EXISTS usuario_web (id integer DEFAULT  NEXTVAL('user_id_seq') NOT  NULL, username varchar, password varchar, cedula varchar, correo varchar, nombre varchar, token varchar, fecha varchar, primary key (id))")
        
        cur.execute("SELECT username FROM usuario_web WHERE cedula = %s", (cedula,))
        result = cur.fetchone()
        if result:
            pass
        else:
            cur.execute("INSERT INTO usuario_web (username, password, cedula, correo, nombre) VALUES (%s, %s, %s, %s, %s)",(cedula,cedula, cedula, email, nombre))
            conn.commit()
        
        cur.execute("SELECT username FROM usuario_web WHERE cedula = %s", (ruc,))
        result = cur.fetchone()
        if result:
            pass
        else:
            cur.execute("INSERT INTO usuario_web (username, password, cedula, correo, nombre) VALUES (%s, %s, %s, %s, %s)",(ruc,ruc, ruc, email_e, nombre_e))
            conn.commit()
            
        cur.execute("SELECT * FROM factura_id_seq;")
        sequence_f = cur.fetchone()
        if sequence_f:
            pass
        else:
            cur.execute("CREATE SEQUENCE factura_id_seq;")    
        cur.execute("CREATE TABLE IF NOT EXISTS factura_web (id integer DEFAULT  NEXTVAL('factura_id_seq') NOT  NULL, cedula varchar, ruc varchar, tipo varchar, fecha varchar, empresa varchar, numero_comprobante varchar, numero_autorizacion varchar, total varchar, path_xml varchar, path_pdf varchar, primary key (numero_autorizacion))")
        
        cur.execute("SELECT cedula FROM factura_web WHERE numero_autorizacion = %s", (auth,))
        result = cur.fetchone()
        if result:
            pass
        else:
            cur.execute("INSERT INTO factura_web (cedula, ruc, tipo, fecha, empresa, numero_comprobante, numero_autorizacion, total, path_xml, path_pdf) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",(cedula, ruc, tipo, fecha, empresa, numero, auth, total, path_xml, path_pdf))
            conn.commit()
        cur.close()
        conn.close()
        
    def send_mail_invoice(self, xml_element, access_key, send_m, server="localhost"):
        MAIL= u"Ud no ha configurado el correo del cliente. Diríjase a: \nTerceros->General->Medios de Contacto"
        pool = Pool()
        empresa = self.company.party.name
        empresa = empresa.replace(' ','_')
        empresa = empresa.lower()
        
        correos = pool.get('party.contact_mechanism')
        correo = correos.search([('type','=','email')])
        InvoiceReport = Pool().get('account.invoice', type='report')
        report = InvoiceReport.execute([self.id], {})
        name_pdf = 'g_r_'+access_key + '.pdf'
        name_xml = 'g_r_'+access_key + '.xml'
        xml_elememt = xml_element.replace('><', '>\n<')
        
        f = open(name_pdf, 'wb')
        f.write(report[1])
        f.close()
        f = open(name_xml, 'wb')
        f.write(xml_elememt)
        f.close()
        
        pdf = MIMEApplication(open(name_pdf,"rb").read())
        pdf.add_header('Content-Disposition', 'attachment', filename=name_pdf)
        email=''
        for c in correo:
            if c.party == self.customer.party:
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
        
        invoice_xml = xml_elememt   
        name = access_key + ".xml"
        part2 = MIMEBase('text', 'plain')
        part2.set_payload(invoice_xml)
        part2.add_header('Content-Disposition', 'attachment', filename= name)

        """
        Outgoing Server Name: smtp.zoho.com
        Port: 465 with SSL or
        Port: 587 with TLS
        """
        #fromaddr= from_email
        fromaddr= from_email
        toaddr= to_email
        msg = MIMEMultipart()
        msg['From'] = fromaddr
        msg['To'] = (toaddr)
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = "COMPROBANTE ELECTRONICO"
        body = "Puede consultar todas sus facturas en nuestro sistema: www.... Este es un correo de prueba"
        msg.attach(MIMEText(body, 'plain'))
        msg.attach(part2)
        msg.attach(pdf)
        server = smtplib.SMTP('smtp.gmail.com:587')
        server.starttls()
        server.login(fromaddr, "arlrfc&&&78")
        text = msg.as_string()
        server.sendmail(fromaddr, toaddr, text)
        server.quit()
        ahora = datetime.datetime.now()
        year = str(ahora.year)
        if ahora.month < 10:
            month = '0'+ str(ahora.month)
        else:
            month = str(ahora.month)
        nuevaruta ='/home/noduxdev/.noduxenvs/nodux34auth/comprobantes/'+empresa+'/'+year+'/'+month +'/'
        
        shutil.copy2(name_pdf, nuevaruta)
        shutil.copy2(name_xml, nuevaruta)
        os.remove(name_pdf)
        os.remove(name_xml)
        return True
        
    def generate_access_key(self):
        fecha = self.create_date.strftime('%d%m%Y')
        tipo_cbte = '06'
        ruc = self.company.party.vat_number
        tipo_amb='1'
        num_cbte= self.code
        cod_num= "12345678"
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
                
    def get_tax_element(self):
        """
        """
        company = self.company
        number = self.code
        #auth = self.journal_id.auth_id
        infoTributaria = etree.Element('infoTributaria')
        etree.SubElement(infoTributaria, 'ambiente').text = "1"
        #SriService.get_active_env()
        
        etree.SubElement(infoTributaria, 'tipoEmision').text = self.company.emission_code
        etree.SubElement(infoTributaria, 'razonSocial').text = self.company.party.name
        etree.SubElement(infoTributaria, 'nombreComercial').text = self.company.party.commercial_name
        etree.SubElement(infoTributaria, 'ruc').text = self.company.party.vat_number
        etree.SubElement(infoTributaria, 'claveAcceso').text = self.generate_access_key()
        etree.SubElement(infoTributaria, 'codDoc').text = "06"
        etree.SubElement(infoTributaria, 'estab').text = number[0:3]
        etree.SubElement(infoTributaria, 'ptoEmi').text = number[4:7]
        etree.SubElement(infoTributaria, 'secuencial').text = number[8:17]
        if self.company.party.addresses:
            etree.SubElement(infoTributaria, 'dirMatriz').text = self.company.party.addresses[0].name
        return infoTributaria
    
    def get_shipment_element(self):
        
        company =  self.company
        customer = self.customer
        infoGuiaRemision = etree.Element('infoGuiaRemision')
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirEstablecimiento').text = self.company.party.addresses[0].name
        if self.company.party.addresses:
            etree.SubElement(infoGuiaRemision, 'dirPartida').text = self.company.party.addresses[0].name   
        etree.SubElement(infoGuiaRemision, 'razonSocialTransportista').text= self.carrier.party.name
        etree.SubElement(infoGuiaRemision, 'tipoIdentificacionTransportista').text= tipoDocumento[self.carrier.party.type_document]
        etree.SubElement(infoGuiaRemision, 'rucTransportista').text= self.carrier.party.vat_number
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
        Invoices = pool.get('account.invoice')
        invoice = Invoices.search([('number','=',num_mod)])
        if invoice:
            pass
        else: 
            self.raise_user_error(ERROR)
        for i in invoice:
            date_mod = i.invoice_date.strftime('%d/%m/%Y')
           
        cod_est = self.cod_estab_destino
        if cod_est <10:
            cod = '00'+str(cod_est)
        if cod_est <100:
            cod = '0'+str(cod_est)
        if cod_est <1000:
            cod = str(cod_est)
            
        company =  self.company
        customer = self.customer
        destinatarios=etree.Element('destinatarios')
        destinatario= etree.Element('destinatario') 
        etree.SubElement(destinatario, 'identificacionDestinatario').text = self.customer.party.vat_number
        etree.SubElement(destinatario, 'razonSocialDestinatario').text = self.customer.party.name
        etree.SubElement(destinatario, 'dirDestinatario').text = self.dir_destinatario
        etree.SubElement(destinatario, 'motivoTraslado').text = self.motivo_traslado
        etree.SubElement(destinatario, 'docAduaneroUnico').text = " "
        etree.SubElement(destinatario, 'codEstabDestino').text = cod
        etree.SubElement(destinatario, 'ruta').text = self.ruta
        etree.SubElement(destinatario, 'codDocSustento').text = "01"
        etree.SubElement(destinatario, 'numDocSustento').text = num_mod
        etree.SubElement(destinatario, 'fechaEmisionDocSustento').text = self.create_date.strftime('%d/%m/%Y') 
        detalles = etree.Element('detalles')
        def fix_chars(code):
            if code:
                code.replace(u'%',' ').replace(u'º', ' ').replace(u'Ñ', 'N').replace(u'ñ','n')
                return code
            return '1'
        detalle = etree.Element('detalle')
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
        """
        """
        sql = "select autorizado_sri, number from account_invoice where state='open' and number < '%s' order by number desc limit 1" % self.number
        self.execute(sql)
        res = self.fetchone()
        return res[0] and True or False
        
    def action_generate_shipment(self):
        """
        """
        PK12 = u'No ha configurado los datos de la empresa. Dirijase a: \n Empresa -> NODUX WS'
        AUTHENTICATE_ERROR = u'Error en datos de ingreso verifique: \nUSARIO Y CONTRASEÑA'
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
        name_r = name.replace(' ','_')
        name_l=name_r.lower()
        name_c = name_l+'.p12'
        if self.company.file_pk12:
            archivo = self.company.file_pk12
        else :
            self.raise_user_error(PK12)
            
        f = open(name_c, 'wb')
        f.write(archivo)
        f.close()
        print usuario, password_u
        authenticate, send_m = s.model.nodux_electronic_invoice_auth.conexiones.authenticate(usuario, password_u, {})
        if authenticate == '1':
            pass
        else:
            self.raise_user_error(AUTHENTICATE_ERROR)
                
        nuevaruta = s.model.nodux_electronic_invoice_auth.conexiones.save_pk12(name_l, {})
        shutil.copy2(name_c, nuevaruta)
        os.remove(name_c)
        guiaRemision1 = self.generate_xml_shipment()
        guiaRemision = etree.tostring(guiaRemision1, enconding = 'utf8', method='xml')
        #validacion del xml (llama metodo validate xml de sri)
        print etree.tostring(guiaRemision,pretty_print=True ,xml_declaration=True, encoding="utf-8") 
        a = s.model.nodux_electronic_invoice_auth.conexiones.validate_xml(guiaRemision, 'out_shipment', {})    
        if a:
                self.raise_user_error(a)
        file_pk12 = base64.encodestring(nuevaruta+'/'+name_c)
        password = base64.encodestring(self.company.password_pk12)
        signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(guiaRemision, file_pk12, password,{})
        #print signed_document
        #envio al sri para recepcion del comprobante electronico
        result = s.model.nodux_electronic_invoice_auth.conexiones.send_receipt(signed_document, {})
        if result != True:
            self.raise_user_error(result)
        time.sleep(WAIT_FOR_RECEIPT)
        # solicitud al SRI para autorizacion del comprobante electronico
        doc_xml, m, auth, path, numero = s.model.nodux_electronic_invoice_auth.conexiones.request_authorization(access_key, name_l, 'out_shipment',{})    
        if doc_xml is None:
            msg = ' '.join(m)
            raise m
                
        if auth == False:
            self.write([self],{ 'estado_sri': 'NO AUTORIZADO'})
            self.raise_user_error(m)
        else:
            self.write([self],{ 'estado_sri': auth, 'path_xml': path+'.xml','numero_autorizacion' : numero, 'path_pdf':path+'.pdf' })
                
        time.sleep(WAIT_FOR_RECEIPT)
        self.send_mail_invoice(doc_xml,access_key, send_m) 
                        
        return access_key
        
    def action_generate_lote_shipment(self):
        """
        """
        LIMIT_TO_SEND = 5
        WAIT_FOR_RECEIPT = 3
        TITLE_NOT_SENT = u'No se puede enviar el comprobante electronico al SRI'
        MESSAGE_SEQUENCIAL = u'Los comprobantes electronicos deben ser enviados al SRI en orden secuencial'
        MESSAGE_TIME_LIMIT = u'Los comprobantes electronicos deben ser enviados al SRI para su autorizacion, en un plazo maximo de 24 horas'
        
        if not self.type in ['out_shipment']:
            print "no disponible para otros documentos"
            pass
        access_key = self.generate_access_key_lote()
        if self.type == 'out_shipment':
            # XML del comprobante electronico: factura
            lote = self.generate_xml_lote_shipment()
            #validacion del xml (llama metodo validate xml de sri)
            inv_xml = DocumentXML(lote, 'lote')
            inv_xml.validate_xml()
            # solicitud de autorizacion del comprobante electronico
            xmlstr = etree.tostring(lote, encoding='utf8', method='xml')            
            inv_xml.send_receipt(xmlstr)
            time.sleep(WAIT_FOR_RECEIPT)
            doc_xml, m, auth = inv_xml.request_authorization_lote(access_key)
            print "esta es la auth", auth
            
            if doc_xml is None:
                msg = ' '.join(m)
                raise m
            if auth == False:
                vals = {'estado_sri': 'NO AUTORIZADO',
                }
            else:
                vals = {'estado_sri': auth.estado,
                }
            self.write([self], vals)    
            time.sleep(WAIT_FOR_RECEIPT)
            self.send_mail_invoice(doc_xml)
            
            if auth== False:
                self.raise_user_error('error',(m,))
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
        password = base64.encodestring(self.company.password_pk12)
        
            
        Invoice = pool.get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        print invoices
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for invoice in invoices:
            print "Factura ",invoice
            factura1 = invoice.generate_xml_invoice()
            factura = etree.tostring(factura1, encoding = 'utf8', method = 'xml')
            #print etree.tostring(factura1, pretty_print = True, xml_declaration=True, encoding="utf-8")
            signed_document = s.model.nodux_electronic_invoice_auth.conexiones.apply_digital_signature(factura, file_pk12, password,{})
            etree.SubElement(comprobantes, 'comprobante').text = etree.CDATA(signed_document)
        lote.append(comprobantes)
        print etree.tostring(lote,pretty_print=True ,xml_declaration=True, encoding="utf-8")
        return lote
    
    
        pool = Pool()
        xades = Xades()
        file_pk12 = base64.encodestring(self.company.electronic_signature)
        password = base64.encodestring(self.company.password_hash)
        Shipment = Pool().get('stock.shipment.out')
        shipments = Shipment.browse(Transaction().context['active_ids'])
        
        lote = etree.Element('lote')
        lote.set("version", "1.0.0")
        etree.SubElement(lote, 'claveAcceso').text = self.generate_access_key_lote()
        etree.SubElement(lote, 'ruc').text = self.company.party.vat_number
        comprobantes = etree.Element('comprobantes')
        for shipment in shipment:
            guiaRemision = self.generate_xml_shipment()
            signed_document = xades.apply_digital_signature(guiaRemision, file_pk12, password)
            print etree.tostring(guiaRemision,pretty_print=True ,xml_declaration=True, encoding="utf-8")
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
