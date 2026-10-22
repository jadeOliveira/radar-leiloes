from .base import SiteAdapter
from .caixa import CaixaAdapter
from .comprei import CompreiAdapter
from .diego_leiloes import DiegoLeiloesAdapter
from .duarte import DuarteAdapter
from .freitas import FreitasAdapter
from .machado import MachadoAdapter
from .hasta import HastaAdapter
from .hasta_publica import HastaPublicaAdapter
from .leiloeiro_publico import LeiloeiroPublicoAdapter
from .mega_leiloes import MegaLeiloesAdapter
from .portalzuk import PortalZukAdapter
from .seu_imovel_bb import SeuImovelBBAdapter
from .sampaio import SampaioAdapter
from .superbid import SuperbidAdapter
from .zampieri import ZampieriAdapter

ADAPTERS = {
    "portalzuk": PortalZukAdapter,
    "caixa": CaixaAdapter,
    "mega_leiloes": MegaLeiloesAdapter,
    "superbid": SuperbidAdapter,
    "diego_leiloes": DiegoLeiloesAdapter,
    "duarte": DuarteAdapter,
    "zampieri": ZampieriAdapter,
    "seu_imovel_bb": SeuImovelBBAdapter,
    "freitas": FreitasAdapter,
    "machado": MachadoAdapter,
    "sampaio": SampaioAdapter,
    "comprei": CompreiAdapter,
    "hasta": HastaAdapter,
    "hasta_publica": HastaPublicaAdapter,
    "leiloeiro_publico": LeiloeiroPublicoAdapter,
}
