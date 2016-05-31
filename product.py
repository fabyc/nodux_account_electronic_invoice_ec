#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import copy

from trytond.model import ModelSQL, fields
from trytond.pyson import Eval, Or
from trytond import backend
from trytond.transaction import Transaction
from trytond.pool import PoolMeta

__all__ = ['Category', 'Template', 'MissingFunction']
__metaclass__ = PoolMeta

_TARIFA = [
    ('', ''),
    ('6', 'No objeto de Impuesto'),
    ('7', 'Exento de IVA'),
]

class MissingFunction(fields.Function):
    '''Function field that will raise the error
    when the value is accessed and is None'''

    def __init__(self, field, error, getter, setter=None, searcher=None,
            loading='lazy'):
        super(MissingFunction, self).__init__(field, getter, setter=setter,
            searcher=searcher, loading=loading)
        self.error = error

    def __copy__(self):
        return MissingFunction(copy.copy(self._field), self.error, self.getter,
            setter=self.setter, searcher=self.searcher)

    def __deepcopy__(self, memo):
        return MissingFunction(copy.deepcopy(self._field, memo), self.error,
            self.getter, setter=self.setter, searcher=self.searcher)

    def __get__(self, inst, cls):
        value = super(MissingFunction, self).__get__(inst, cls)
        if inst is not None and value is None:
            inst.raise_user_error(self.error, (inst.name, inst.id))
        return value


class Category:
    __name__ = 'product.category'
        
    iva_parent = fields.Boolean('Usar tarifa del padre', help='Usar el tipo de tarifa definido en el padre')

    ice = fields.Boolean('Aplica Impuesto a los Consumos Especiales (ICE)',
        help='Seleccione en caso que el producto aplique a Impuesto a los Consumos Especiales(ICE)',states={
            'invisible': Eval('iva_parent',False),
            })
        
    iva_tarifa = fields.Selection(_TARIFA, 'Tarifa IVA', help = "Tarifa correspondiente a IVA", states={
            'invisible': Eval('iva_parent',False),
            })
            
    ice_tarifa = fields.Many2One('account.tax.special', 'Tarifa ICE', help = "Tarifa correspondiente a ICE", states={
            'invisible': ~Eval('ice',True),
            })

    iva_tarifa_used = fields.Function(fields.Selection(_TARIFA,'Tarifa correspondiente a IVA'), 'get_iva')
    ice_tarifa_used = fields.Function(fields.Many2One('account.tax.special', 'Tarifa ICE'), 'get_ice')
    
    @classmethod
    def __setup__(cls):
        super(Category, cls).__setup__()
        
        cls.parent.states['required'] = Or(
            cls.parent.states.get('required', False),
            Eval('iva_parent', False))
        cls.parent.depends.extend(['iva_parent'])
    
    @staticmethod
    def default_ice():
        return False
    
    @staticmethod
    def default_iva_parent():
        return False

    def get_ice(self, name):
        if self.iva_parent:
            # Use __getattr__ to avoid raise of exception
            ice = self.parent.__getattr__(name)
        else:
            ice = getattr(self, name[:-5])
        return ice.id if ice else ""

    def get_iva(self, name):
        if self.iva_parent:
            iva = self.parent.__getattr__(name)
        else:
            iva = getattr(self, name[:-5])
        return iva if ice else ""

class Template:
    __name__ = 'product.template'
    iva_category = fields.Boolean('Usar tarifa de la categoria',
        help='Usar el tipo de tarifa definido en la categoria')
        
    ice = fields.Boolean('Aplica Impuesto a los Consumos Especiales (ICE)',
        help='Seleccione en caso que el producto aplique a Impuesto a los Consumos Especiales(ICE)',states={
            'invisible': Eval('iva_category',False),
            })
        
    iva_tarifa = fields.Selection(_TARIFA, 'Tarifa IVA', help = "Tarifa correspondiente a IVA", states={
            'invisible': Eval('iva_category',False),
            })
    
    ice_tarifa = fields.Many2One('account.tax.special', 'Tarifa ICE', help = "Tarifa correspondiente a ICE", states={
            'invisible': ~Eval('ice',True),
            })

    iva_tarifa_used = fields.Function(fields.Selection(_TARIFA,'Tarifa correspondiente a IVA'), 'get_iva')
    ice_tarifa_used = fields.Function(fields.Many2One('account.tax.special', 'Tarifa ICE'), 'get_ice')
    
    @classmethod
    def __setup__(cls):
        super(Template, cls).__setup__()
        
        cls.category.states['required'] = Or(
            cls.category.states.get('required', False),
            Eval('iva_category', False))
        cls.category.depends.extend(['iva_category'])

    @staticmethod
    def default_ice():
        return False
    
    @staticmethod
    def default_iva_category():
        return False
        
    def get_ice(self, name):
        if self.iva_category:
            # Use __getattr__ to avoid raise of exception
            ice = self.category.__getattr__(name)
        else:
            ice = getattr(self, name[:-5])
        return ice.id if ice else ""

    def get_iva(self, name):
        if self.iva_category:
            iva = self.category.__getattr__(name)
        else:
            iva = getattr(self, name[:-5])
        return iva if iva else ""
