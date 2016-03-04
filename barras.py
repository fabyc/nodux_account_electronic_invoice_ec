#Modulo para generar codigos de barra en Entrelazado 2 de 5 (I25)"
import os
import sys
import traceback
from PIL import Image, ImageFont, ImageDraw


class CodigoBarra:
    _public_methods_ = ['GenerarImagen','DigitoVerificadorModulo11']
    
    def GenerarImagen(self, codigo, archivo = "barras.png",
                      basewidth=3, width=None, height=30, extension = "PNG"):
        wide = basewidth
        narrow=basewidth/ 3
        #codigos ancho/angosotos (wide/narrow) para los digitos
        #basado en Juego completo de caracteres para el codigo 2 de 5 entrelazado n->d(delgado); w->a(ancho)
        bars = ("nnwwn","wnnnw","nwnnw", "wwnnn", "nnwnw", "wnwnn", "nwwnn",
                "nnnww", "wnnwn", "nwnwn", "nn", "wn")
        #agregar un 0 al principio si el numero de digitos es impar
        if len(codigo) % 2 :
            codigo = "0" + codigo
        if not width:
            width = (len(codigo) * 3) * basewidth + (10 * narrow)
        im = Image.new("1",(width, height))
        codigo = "::" + codigo.lower() + ";:" #A y Z en el original
        draw = ImageDraw.Draw(im)
        draw.rectangle(((0,0), (im.size[0], im.size[1])), fill= 256)
        xpos = 0
        for i in range(0,len(codigo),2):
            bar = ord(codigo[i]) - ord("0")
            space = ord(codigo[i + 1]) - ord("0")
            seq = ""
            for s in range(len(bars[bar])):
                seq = seq + bars[bar][s] + bars[space][s]
            for s in range(len(seq)):
                if seq[s] == "n":
                    width =  narrow
                else:
                    width = wide
                #dibujar barras impares (las pares son espacios)
                if not s % 2:
                    draw.rectangle(((xpos,0),(xpos+width-1,height)),fill=0)
                xpos= xpos + width
        im.save(archivo, extension.upper())
        return True
    
    def DigitoVerificadorModulo11(self, codigo):
        codigo= codigo.strip()
        if not codigo or not codigo.isdigit():
            return ''
        clave = []
        for c in codigo:
            clave.append(int(c))
        clave.reverse()
        factor = [2,3,4,5,6,7]
        etapa1 = sum ([n*factor[i%6] for i,n in enumerate(clave)])
        etapa2 = etapa1 % 11
        digito = 11 - (etapa2)
        return str (digito)
        
if __name__ == '__main__':
           codigobarra = CodigoBarra()
           
           if '--barras' in sys.argv:
               barras = sys.argv[sys.argv.index("--barras")+1]
           else:
                fecha = 11112015
                ruc = 1105154502001
                tipo_cbte = 04
                tipo_amb = 1
                serie= 000007
                num_cbte= 000000006
                cod_num = 00000003
                tipo_emision = 1
                barras = '%s%02d%s%s%06d%09d%08d%s' % (fecha, tipo_cbte, ruc, tipo_amb, serie, num_cbte, cod_num, tipo_emision)
           if not '--noverificador' in sys.argv:
                barras = barras + codigobarra.DigitoVerificadorModulo11(barras)    
            
           if '--archivo' in sys.argv:
                archivo = sys.argv[sys.argv.index("--archivo")+1]
                extension = os.path.splitext(archivo)[1]
                extension = extension.upper()[1:]
                if extension == 'JPG':
                    extension = 'JPEG'
           else:
                archivo= "codigo-barras.png"
                extension = 'PNG'
            
           print "barras", barras
           print "archivo", archivo
           codigobarra.GenerarImagen(barras, archivo, extension=extension)
            
           if not '--mostrar' in sys.argv:
                pass
           elif sys.platform=="linux2":
                os.system("eog ""%s""" % archivo)
           else:
                os.startfile(archivo)
                fecha = 25101991
           
