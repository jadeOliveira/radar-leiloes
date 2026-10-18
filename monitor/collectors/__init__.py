from .base import SiteAdapter
from .caixa import CaixaAdapter
from .comprei import CompreiAdapter
from .diego_leiloes import DiegoLeiloesAdapter
from .freitas import FreitasAdapter
from .mega_leiloes import MegaLeiloesAdapter
from .portalzuk import PortalZukAdapter
from .seu_imovel_bb import SeuImovelBBAdapter
from .superbid import SuperbidAdapter

ADAPTERS = {
    "portalzuk": PortalZukAdapter,
    "caixa": CaixaAdapter,
    "mega_leiloes": MegaLeiloesAdapter,
    "superbid": SuperbidAdapter,
    "diego_leiloes": DiegoLeiloesAdapter,
    "seu_imovel_bb": SeuImovelBBAdapter,
    "freitas": FreitasAdapter,
    "comprei": CompreiAdapter,
}
