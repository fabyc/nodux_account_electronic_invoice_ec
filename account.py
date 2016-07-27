#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, MatchMixin, fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['FormaPago','Configuration']
__metaclass__ = PoolMeta

class FormaPago(ModelSQL, ModelView):
    'Forma Pago'
    __name__ = 'account.formas_pago'
    name = fields.Char('Forma de pago', size=None, required=True, translate=True)
    code = fields.Char('Codigo', size=None, required=True)

    @classmethod
    def __setup__(cls):
        super(FormaPago, cls).__setup__()

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

class Configuration:
    'Account Configuration'
    __name__ = 'account.configuration'

    lote = fields.Boolean('Enviar comprobantes por lote')

    @classmethod
    def __setup__(cls):
        super(Configuration, cls).__setup__()

    @staticmethod
    def default_lote():
        return False
