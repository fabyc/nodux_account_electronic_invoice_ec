#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
import datetime
from decimal import Decimal
from sql.aggregate import Sum

from trytond.model import ModelView, ModelSQL, MatchMixin, fields
from trytond.wizard import Wizard, StateView, StateAction, Button
from trytond import backend
from trytond.pyson import Eval, If, Bool, PYSONEncoder
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta

__all__ = ['TaxElectronic', 'TaxSpecial', 'Tax']
__metaclass__ = PoolMeta

_IMPUESTO = [
    ('', ''),
    ('1', 'RENTA'),
    ('2', 'IVA'),
    ('6', 'ISD'),
]

class TaxElectronic(ModelSQL, ModelView):
    'Tax Electronic'
    __name__ = 'account.tax.electronic'
    name = fields.Char('Concepto Retencion', size=None, required=True, translate=True)
    code = fields.Char('Codigo', size=None, required=True)

    @classmethod
    def __setup__(cls):
        super(TaxElectronic, cls).__setup__()

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('code',) + tuple(clause[1:]),
            (cls._rec_name,) + tuple(clause[1:]),
            ]

    def get_rec_name(self, name):
        if self.code:
            return self.code + ' - ' + self.name
        else:
            return self.name

class TaxSpecial(ModelSQL, ModelView):
    'Impuesto a los Consumos especiales'
    __name__ = 'account.tax.special'
    name = fields.Char('Concepto Impuesto Consumos Especiales', size=None, required=True, translate=True)
    code = fields.Char('Codigo', size=None, required=True)

    @classmethod
    def __setup__(cls):
        super(TaxSpecial, cls).__setup__()

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('code',) + tuple(clause[1:]),
            (cls._rec_name,) + tuple(clause[1:]),
            ]

    def get_rec_name(self, name):
        if self.code:
            return self.code + ' - ' + self.name
        else:
            return self.name

class Tax(ModelSQL, ModelView):
    __name__ = 'account.tax'

    code_electronic = fields.Many2One('account.tax.electronic', "Codigo para Retencion-Comprobantes Electronicos", 
        help="Seleccionar el codigo por impuesto de acuerdo al porcentaje de retencion")
    code_withholding = fields.Selection(_IMPUESTO, 'Impuesto asignado para la retencion', help="Seleccionar el codigo de impuesto asignados para la retencion")

    @classmethod
    def __setup__(cls):
        super(Tax, cls).__setup__()

    @staticmethod
    def default_code_withholding():
        return ''
