#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, MatchMixin, fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Configuration']
__metaclass__ = PoolMeta


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
