import { useEffect, useMemo, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ExternalLink, Filter, House, Search, SlidersHorizontal } from 'lucide-react';

type Auction = {
  id: string; title: string; city: string; state: string; address?: string;
  propertyType?: string; auctioneer: string; url: string; price?: number | null;
  appraisalValue?: number | null; discountPercent?: number | null;
  areaM2?: number | null; auctionDate?: string | null; occupancy?: string | null;
  collectedAt?: string;
};
type Dataset = { updatedAt?: string | null; source?: string; auctions?: Auction[] };
const money = (value?: number | null) => value == null ? 'Valor não informado' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value);

export default function App() {
  const [data, setData] = useState<Dataset>({ auctions: [] });
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('Todas as cidades');
  const [type, setType] = useState('Todos os tipos');
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/auctions.json`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('dados indisponíveis')))
      .then((value: Dataset) => setData(value))
      .catch(() => setData({ auctions: [] }))
      .finally(() => setLoading(false));
  }, []);

  const auctions = data.auctions ?? [];
  const cities = [...new Set(auctions.map((item) => item.city).filter(Boolean))].sort();
  const types = [...new Set(auctions.map((item) => item.propertyType).filter(Boolean))].sort() as string[];
  const filtered = useMemo(() => auctions.filter((item) => {
    const matchesQuery = `${item.title} ${item.city} ${item.address ?? ''}`.toLocaleLowerCase('pt-BR').includes(query.toLocaleLowerCase('pt-BR'));
    const matchesCity = city === 'Todas as cidades' || item.city === city;
    const matchesType = type === 'Todos os tipos' || item.propertyType === type;
    const isPriority = (item.price ?? Infinity) <= 800000 && (item.discountPercent ?? 0) >= 30;
    return matchesQuery && matchesCity && matchesType && (!priorityOnly || isPriority);
  }), [auctions, query, city, type, priorityOnly]);

  const updated = data.updatedAt ? new Date(data.updatedAt).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }) : 'Ainda não executada';

  return <main className="page">
    <header className="topbar"><a className="brand" href="#top"><span className="brand-mark"><House size={19} /></span><span>RADAR<span className="brand-light"> DE LEILÕES</span></span></a><span className="top-note">SANTA CATARINA <i /> ATUALIZAÇÃO DIÁRIA</span></header>
    <section className="hero" id="top">
      <div className="hero-copy"><div className="eyebrow"><span className="eyebrow-line" /> MONITORAMENTO IMOBILIÁRIO</div><h1>Encontre o próximo<br /><em>bom negócio.</em></h1><p>Uma leitura clara das oportunidades de leilões imobiliários em Santa Catarina.</p></div>
      <div className="hero-side"><div className="hero-index">01 <span>/ 01</span></div><div className="hero-rule" /><p>Começando por<br /><strong>Rio do Sul, SC</strong></p><a href="https://www.portalzuk.com.br/leilao-de-imoveis" target="_blank" rel="noreferrer">Fonte oficial <ExternalLink size={13} /></a></div>
    </section>
    <section className="stats" aria-label="Resumo"><div className="stat"><span>IMÓVEIS ACOMPANHADOS</span><strong>{auctions.length.toString().padStart(2, '0')}</strong></div><div className="stat"><span>OPORTUNIDADES PRIORITÁRIAS</span><strong>{auctions.filter((x) => (x.price ?? Infinity) <= 800000 && (x.discountPercent ?? 0) >= 30).length.toString().padStart(2, '0')}</strong></div><div className="stat update-stat"><span>ÚLTIMA COLETA</span><strong>{updated}</strong><small>{loading ? 'Carregando dados…' : 'Horário de Brasília'}</small></div></section>
    <section className="list-section"><div className="section-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> OPORTUNIDADES</div><h2>Imóveis em <em>destaque</em></h2></div><span className="result-count">{filtered.length} {filtered.length === 1 ? 'imóvel' : 'imóveis'}</span></div>
      <div className="filters"><label className="search"><Search size={17} /><input aria-label="Buscar imóvel" placeholder="Buscar por bairro ou endereço" value={query} onChange={(event) => setQuery(event.target.value)} /></label><label className="select-wrap"><SlidersHorizontal size={15} /><select aria-label="Filtrar cidade" value={city} onChange={(event) => setCity(event.target.value)}><option>Todas as cidades</option>{cities.map((item) => <option key={item}>{item}</option>)}</select></label><label className="select-wrap"><Filter size={15} /><select aria-label="Filtrar tipo" value={type} onChange={(event) => setType(event.target.value)}><option>Todos os tipos</option>{types.map((item) => <option key={item}>{item}</option>)}</select></label><button className={`priority-toggle ${priorityOnly ? 'active' : ''}`} onClick={() => setPriorityOnly(!priorityOnly)}><span className="toggle-dot" /> Priorizar até R$ 800 mil e 30%+ de desconto</button></div>
      {filtered.length ? <div className="cards">{filtered.map((item) => {
        const priority = (item.price ?? Infinity) <= 800000 && (item.discountPercent ?? 0) >= 30;
        return <article className="property" key={item.id}><div className="property-top"><span className="property-type">{item.propertyType || 'Imóvel'} <span>·</span> {item.city}/{item.state}</span>{priority && <span className="badge"><ArrowDownRight size={13} /> PRIORIDADE</span>}</div><h3>{item.title}</h3><p className="address">{item.address || 'Endereço não informado'}</p><div className="property-metrics"><div><span>LANCE MÍNIMO</span><strong>{money(item.price)}</strong></div><div><span>DESCONTO</span><strong>{item.discountPercent != null ? `${item.discountPercent}%` : '—'} {item.discountPercent != null && <ArrowDownRight size={14} />}</strong></div><div><span>ÁREA</span><strong>{item.areaM2 ? `${item.areaM2} m²` : '—'}</strong></div></div><div className="property-bottom"><span>{item.auctioneer}{item.auctionDate ? ` · ${new Date(item.auctionDate).toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' })}` : ''}</span><a href={item.url} target="_blank" rel="noreferrer">Ver leilão <ArrowUpRight size={15} /></a></div></article>;
      })}</div> : <div className="empty"><div className="empty-icon"><Search size={20} /></div><h3>{loading ? 'Buscando oportunidades…' : auctions.length === 0 ? 'A coleta diária ainda não encontrou imóveis.' : 'Nenhum imóvel com esses filtros.'}</h3><p>{auctions.length === 0 ? 'Os dados aparecem aqui quando o coletor identificar anúncios ativos na fonte monitorada. A lista não usa imóveis fictícios.' : 'Ajuste os filtros para ver outros resultados.'}</p>{auctions.length === 0 && <a href="https://www.portalzuk.com.br/leilao-de-imoveis" target="_blank" rel="noreferrer">Consultar Portal Zuk <ExternalLink size={14} /></a>}</div>}
    </section>
    <footer><span>RADAR DE LEILÕES <span className="footer-sep">/</span> MVP</span><p>Dados coletados de páginas públicas. Confirme informações e condições no anúncio e no edital oficiais antes de qualquer decisão.</p><span>Feito para informar, não para decidir.</span></footer>
  </main>;
}
