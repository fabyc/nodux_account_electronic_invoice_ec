=============
Terceros
=============
En el Menú Terceros/Configuración/Empresas se deben configurar los campos
agregados en la pestaña NODUX WS los cuales son necesarios para la conexión
con el Servidor Web Autorizador y para Generar los Comprobantes Electrónicos.
Para mantener la seguridad e integridad de los datos del cliente, se ha considerado
que se guarden encriptados en la base de datos.
-Usuario Ws -> cada cliente tiene su usuario asignado, que es el que deberá 
ingresarse en este campo.
-Password Ws -> con el usuario descrito anteriormente se entrega también una
contraseña que se ingresará en este campo (Si ud. cambia estos valores debe
comunicarse con el Administrador del Sistema).
-Archivo de la Firma digital-> se tiene que agregar el archivo de la Firma
Digital (extensión .p12) el cual es necesario para poder firmar los comprobantes
electrónicos.
-Password de la Firma Digital-> es necesaria la contraseña de la Firma Digital
para poder acceder y firmar los comprobantes, en caso que la contraseña o archivo 
sean incorrectos se presentará un error en pantalla, y no podrá enviar comprobantes
electrónicos para la autorización, ya que el SRI lo considera como un Archivo que no
cumple con la estructura.
-Logo de su empresa-> es necesario agregar la imagen del logo de la empresa 
para que se incluya al Generar el Comprobante.

En el Menú Terceros/Terceros en la pestaña Contabilidad se han agregado campos 
necesarios para la facturación electrónica, los cuales deben ser configurados para 
que los comprobantes se generen sin presentar errores.
Obligado a Llevar contabilidad-> Este campo aparecerá cuando el tercero ingresado 
tenga como documento de identificación RUC. Si el tercero es obligado a llevar 
contabilidad se seleccionará Si.
Contribuyente Especial-> Si el tercero ingresado es Obligado a llevar contabilidad
aparacerá este nuevo campo en el que se deberá indicar si es o no contribuyente especial.
Contribuyente Especial Nro->Si el tercero es contribuyente especial, se deberá
ingresar el número asignado por el Servicio de Rentas Internas(SRI).
Nombre Comercial-> Ingresar el nombre Comercial, si el tercero no tiene nombre 
comercial dejar el campo en blanco.

En el Menú Terceros/Terceros/General se ha agregado una configuración para que 
se ingrese por lo menos un correo electrónico para cada tercero, ya que es necesario
para enviar los comprabantes electrónicos, se tomará en cuenta que el correo ingresado
cumpla con la estructura válida para un correo-> (example@mail.com).

=============
Productos
=============
En el menú Productos/Producto se ha agregado una nueva pestaña en la que se incluye:
-Usar el tipo de impuesto de la Categoria-> se utilizará el tipo de impuesto que se haya 
configurado en la Categoria del Producto, es necesario recordar que si se selecciona este
campo, será Obligatorio ingresar una categoria para el Producto, y los campos siguientes
se ocultaran ya que no será necesario configurarlos nuevamente.
Tarifa IVA-> Si no se ha seleccionado el campo: Usar el tipo de impuesto de la Categoria, 
se deberá indicar que tipo de tarifa de IVA tiene el producto. 
Aplica Impuestos a consumos Especiales-> Si el producto también aplica Impuesto de Consumos
Especiales, se seleccionará este campo.
Tarifa ICE-> Si selecciona el campo anterior (Aplica Impuestos a consumos Especiales)
aparecerá este nuevo campo en el que deberá seleccionar la tarifa de ICE que se aplica al
producto.

=============
Financiero
=============
=============
Impuestos
=============

En el Menú Financiero/Configuración/Impuestos se ha agregado:
-Código de Impuestos Retención-Comprobantes: Se ha generado una plantilla en la que se han
agregado los impuestos de Retención con sus respectivos cógidos, de acuerdo a la normativa
vigente del SRI. En caso que requiera algun impuesto que no se encuentra en la lista, podrá 
crearlo sin inconveniente.
-Impuesto a los Consumos especiales: Se ha generado una plantilla en la que se han
agregado los Impuestos a los Consumos especiales (para los productos), de acuerdo a la normativa
vigente del SRI. En caso que requiera algun impuesto que no se encuentra en la lista, podrá 
crearlo sin inconveniente.

=============
Facturas
=============
En el menú Financiero/Facturas se ha agregado una pestado Facturación Electrónica Ecuador,
aqui se debera configurar:
-Envio de Facturas por lote-> Estará configurado para que las facturas se envien por lote,
si no se deshabilita la opción, puede hacer el envío en la acción ENVIAR SRI. 
Cuando el usuario deshabilita la opción de Envío de Facturas por Lote, al momento de presionar
el botón Contabilizar se hará la conexión con el WS-Nodux en caso que el cliente no se encuentre
activo, o sus datos de conexión no sean correctos se presentará un mensaje indicando el error. 
Si no se recibió un error el comprobante será firmado y se establecerá la conexión con 
los Servidores del SRi para proceder al envío del comprobante, si luego de enviar el comprobante 
firmado al SRI no se ha presentado un error se preocede a enviar el comprobante para su Autorización, 
si el comprobante ha sido AUTORIZADO se hace el envío del correo electrónico al cliente y se 
guardan los datos necesarios para presentarse en el aplicativo WEB. Caso contrario deberá corregir
la factura y enviarla nuevamente para que sea autorizada.

-Estado de facturación Electrónica-> El SRI luego de recibir los comprobantes electrónicos,
realiza la verificación y su autorización, es importante recordar que los comprobantes 
pueden tener algún error y no serán autorizados, para saber cual es el estado del comprobante
se puede revisar en este campo, el cual puede ser: AUTORIZADO o NO AUTORIZADO.

Se ha reemplazado el formato del Comprobante Electrónico para que se adapte a los requerimientos
del SRI.

=============
Inventario
=============
En el menú Inventario/Envios a Cliente se ha agregado una nueva pestaña-> Facturación
Electrónica Ecuador en el que se deberá configurar:
-Enviar Guía de Remisión al SRI-> Si desea enviar la Guía de Remisión al Servicio
de Rentas Internas, deberá seleccionar este campo. Al seleccionarlo observará que se 
aparecerán campos que son necesarios para emitir comprobantes electrónicos, se describen 
a continuación.
--Transporte: Se debe seleccionar el transportista que hará el traslado de la mercaderia,
si no se ha creado antes desde el menú Transportes se puede crear en el momento de emitir
la guía de remisión.
--Placa del Transporte: Numero de Placa del medio de Transporte que traslada la mercadería.
--Número del Documento de Sustento: Es necesario ingresar el número de Factura a la cual
hace referencia la entrega.
--Código de Establecimiento de destino: Ingresar el Cógido del Establecimiento al que se tiene
previsto que llegará la mercadería.
--Ruta: Indicar la ruta por la que se hará el traslado de la mercadería.

=============
Usuario
=============
En el menú Usuarios/Usuarios se ha agregado una pestaña Conexión WS-Nodux en la que se deberán
configurar los siguientes campos para tener conexión con el Servidor Web de Nodux, estos campos
serán visible solo para el usuario administrador, y serán proporcionados por el Administrador de
Nodux.
-Protocolo de Comunicación: Se debe seleccionar el protocolo mediante el cual se establecerá 
la comunicación entre el cliente y el Servidor Web de Nodux.
-Puerto para conexión con WS-Nodux: Ingresar el puerto que haya indicado el administrador de 
Nodux.
-Dirección para conexión con WS-Nodux: Dirección en el que está el servidor web de Nodux.
-Nombre de la Base de Datos: Indicar la base de datos a la que se hará la conexión para emitir
comprobantes electrónicos.
-Password de la Base de Datos: Contraseña de la base de datos ingresada anteriormente.
-usuario de la Base de Datos: Usuario con la que se realizará la conexión a la base de datos.

Nota: Cada módulo es adaptable a los requerimientos del cliente
