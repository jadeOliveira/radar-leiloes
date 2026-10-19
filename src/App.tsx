import { useEffect, useMemo, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ExternalLink, Filter, House, Search, SlidersHorizontal } from 'lucide-react';

type AuctionEvent = { date?: string; time?: string | null; minimum_bid_brl?: number | null; stage?: string };
type Property = {
  id: string; city: string; state: string; address?: string | null; neighborhood?: string | null;
  property_type?: string | null; auctioneer?: string | null; official_url?: string | null;
  source_listing_url?: string | null; validation_status?: string | null;
  image_urls?: string[];
  first_minimum_bid_brl?: number | null; second_minimum_bid_brl?: number | null;
  current_minimum_bid_brl?: number | null; source_listing_price_brl?: number | null; appraisal_value_brl?: number | null;
  discount_on_appraisal_percent?: number | null; area_privative_m2?: number | null;
  occupancy?: string | null; status?: string; classification?: 'A' | 'B'; risk_flags?: string[];
  auction_events?: AuctionEvent[]; first_seen_at?: string | null; last_checked_at?: string | null;
  newly_discovered_at?: string | null;
};
type SourceStatus = { source_id: string; name: string; status: string; last_success_at?: string; error?: string };
type Dataset = { updated_at?: string | null; cities?: string[]; priority?: { max_bid_brl?: number; min_discount_percent?: number }; sources?: SourceStatus[]; properties?: Property[] };
type RunReport = { status?: string; started_at?: string; finished_at?: string; data_status?: 'updated' | 'unchanged' | 'unavailable'; data_updated_at?: string | null; new_property_ids?: string[]; counts?: { new_listings?: number; changed_listings?: number; sources_succeeded?: number; sources_partial?: number; sources_failed?: number }; sources?: SourceStatus[] };
const money = (value?: number | null) => value == null ? 'Não informado' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value);
const date = (value?: string | null) => {
  if (!value) return '—';
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const parsed = dateOnly ? new Date(Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]), 12)) : new Date(value);
  return parsed.toLocaleDateString('pt-BR', { timeZone: dateOnly ? 'UTC' : 'America/Sao_Paulo' });
};
const brazilToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const isRecentNew = (property: Property) => Boolean(property.newly_discovered_at && Date.parse(property.newly_discovered_at) >= Date.now() - 7 * 86400000);
const futureAuctionDate = (property: Property, today: string) => property.auction_events?.map((event) => event.date).filter((value): value is string => typeof value === 'string' && value >= today).sort()[0];
const auctionEvent = (property: Property, today: string) => {
  const events = [...(property.auction_events ?? [])].filter((event) => event.date).sort((left, right) => (left.date ?? '').localeCompare(right.date ?? ''));
  return events.find((event) => (event.date ?? '') >= today) ?? events.at(-1);
};
const displayStatus = (property: Property, today: string) => property.status === 'unknown' && futureAuctionDate(property, today) ? 'scheduled_unverified' : property.status ?? 'unknown';

function PropertyPhoto({ property }: { property: Property }) {
  const [failed, setFailed] = useState(false);
  const image = property.image_urls?.[0];
  if (!image || failed) return <div className="property-image-placeholder"><House size={22} /><span>Foto não disponível</span></div>;
  return <img className="property-image" src={image} alt={`Foto do imóvel em ${property.city}`} loading="lazy" onError={() => setFailed(true)} />;
}

export default function App() {
  const [data, setData] = useState<Dataset>({ properties: [] });
  const [lastRun, setLastRun] = useState<RunReport>({});
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('Todas as cidades');
  const [type, setType] = useState('Todos os tipos');
  const [category, setCategory] = useState('Todas');
  const [occupancy, setOccupancy] = useState('Todas');
  const [risk, setRisk] = useState('Todos');
  const [dateWindow, setDateWindow] = useState('Todas');
  const [statusScope, setStatusScope] = useState('new');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [minDiscount, setMinDiscount] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = (name: string): Promise<Dataset> => fetch(`${import.meta.env.BASE_URL}data/${name}`, { cache: 'no-store' }).then((response) => response.ok ? response.json() : {});
    Promise.all([load('properties.json'), load('last-run.json')])
      .then(([properties, run]) => { setData({ ...properties, sources: run.sources ?? properties.sources }); setLastRun(run as RunReport); })
      .catch(() => setData({ properties: [] }))
      .finally(() => setLoading(false));
  }, []);

  const properties = data.properties ?? [];
  const cities = data.cities?.length ? data.cities : [...new Set(properties.map((item) => item.city).filter(Boolean))].sort();
  const types = [...new Set(properties.map((item) => item.property_type).filter(Boolean))].sort() as string[];
  const filtered = useMemo(() => {
    const today = brazilToday();
    const matchesScope = (item: Property) => {
      const status = displayStatus(item, today);
      if (statusScope === 'new') return isRecentNew(item);
      if (statusScope === 'all') return true;
      if (statusScope === 'opportunities') return status === 'active' || status === 'scheduled_unverified';
      return status === 'active';
    };
    const matches = properties.filter((item) => {
      const text = `${item.city} ${item.address ?? ''} ${item.neighborhood ?? ''} ${item.property_type ?? ''}`.toLocaleLowerCase('pt-BR');
      const bid = item.current_minimum_bid_brl;
      const nextDate = futureAuctionDate(item, today);
      const daysToAuction = nextDate ? (new Date(`${nextDate}T12:00:00-03:00`).getTime() - Date.now()) / 86400000 : null;
      const activeCategory = item.classification === 'A';
      return matchesScope(item)
        && text.includes(query.toLocaleLowerCase('pt-BR'))
        && (city === 'Todas as cidades' || item.city === city)
        && (type === 'Todos os tipos' || item.property_type === type)
        && (category === 'Todas' || item.classification === category)
        && (occupancy === 'Todas' || (occupancy === 'Desconhecida' ? !item.occupancy : item.occupancy === occupancy))
        && (risk === 'Todos' || (risk === 'Com alertas' ? Boolean(item.risk_flags?.length) : !item.risk_flags?.length))
        && (dateWindow === 'Todas' || (daysToAuction !== null && daysToAuction >= 0 && daysToAuction <= Number(dateWindow)))
        && (minPrice === '' || (bid !== null && bid !== undefined && bid >= Number(minPrice)))
        && (maxPrice === '' || (bid !== null && bid !== undefined && bid <= Number(maxPrice)))
        && (minDiscount === '' || (item.discount_on_appraisal_percent !== null && item.discount_on_appraisal_percent !== undefined && item.discount_on_appraisal_percent >= Number(minDiscount)))
        && (category !== 'A' || activeCategory);
    });
    return matches.sort((left, right) => {
      const cityOrder = left.city.localeCompare(right.city, 'pt-BR');
      if (cityOrder) return cityOrder;
      const leftDate = auctionEvent(left, today)?.date ?? '9999-12-31';
      const rightDate = auctionEvent(right, today)?.date ?? '9999-12-31';
      return leftDate.localeCompare(rightDate) || left.id.localeCompare(right.id);
    });
  }, [properties, query, city, type, category, occupancy, risk, dateWindow, minPrice, maxPrice, minDiscount, statusScope]);
  const today = brazilToday();
  const activeCount = properties.filter((item) => displayStatus(item, today) === 'active').length;
  const upcomingCount = properties.filter((item) => displayStatus(item, today) === 'scheduled_unverified').length;
  const lastUpdate = data.updated_at ? new Date(data.updated_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }) : 'Sem coleta válida';
  const operationalSources = (data.sources ?? []).filter((source) => source.status === 'success' || source.status === 'partial').length;
  const newInLastWeek = properties.filter(isRecentNew).length;
  const lastRunTime = lastRun.finished_at ? new Date(lastRun.finished_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }) : 'indisponível';
  const dataStatusText = lastRun.data_status === 'unchanged'
    ? 'Nenhum imóvel novo ou alteração relevante nesta coleta.'
    : lastRun.data_status === 'unavailable'
      ? 'Nenhuma fonte respondeu; os anúncios anteriores foram preservados.'
      : lastRun.data_status === 'updated'
        ? `${lastRun.counts?.new_listings ?? 0} novo(s) e ${lastRun.counts?.changed_listings ?? 0} alterado(s) nesta coleta.`
        : 'Aguardando o próximo relatório da coleta.';

  return <main className="page">
    <header className="topbar"><a className="brand" href="#top"><span className="brand-mark"><House size={19} /></span><span>RADAR<span className="brand-light"> DE LEILÕES</span></span></a><span className="top-note">SANTA CATARINA <i /> MONITORAMENTO DIÁRIO</span></header>
    <section className="hero" id="top">
      <div className="hero-copy"><div className="eyebrow"><span className="eyebrow-line" /> MONITORAMENTO IMOBILIÁRIO</div><h1>Encontre o próximo<br /><em>bom negócio.</em></h1><p>Oportunidades em leilões e vendas públicas nas cidades monitoradas de Santa Catarina.</p></div>
      <div className="hero-side"><div className="hero-index">{String(operationalSources).padStart(2, '0')} <span>/ {(data.sources ?? []).length.toString().padStart(2, '0')} fontes ativas</span></div><div className="hero-rule" /><p>Cidades<br /><strong>{cities.length} em Santa Catarina</strong></p><a href="https://www.portalzuk.com.br/leilao-de-imoveis/u/todos-imoveis/sc" target="_blank" rel="noreferrer">Fontes oficiais <ExternalLink size={13} /></a></div>
    </section>
    <section className="stats" aria-label="Resumo"><div className="stat"><span>ATIVOS · SINAL DA FONTE</span><strong>{activeCount.toString().padStart(2, '0')}</strong></div><div className="stat"><span>PRÓXIMOS · A CONFIRMAR</span><strong>{upcomingCount.toString().padStart(2, '0')}</strong></div><div className="stat"><span>OPORTUNIDADES PRIORITÁRIAS</span><strong>{properties.filter((item) => item.classification === 'A').length.toString().padStart(2, '0')}</strong></div><div className="stat update-stat"><span>ÚLTIMA COLETA VÁLIDA</span><strong>{lastUpdate}</strong><small>America/Sao_Paulo</small></div></section>
    <section className={`freshness-banner freshness-${lastRun.data_status ?? 'unknown'}`} aria-live="polite"><strong>{dataStatusText}</strong><span>Relatório da coleta: {lastRunTime} · Dados dos anúncios: {lastUpdate}{newInLastWeek ? ` · ${newInLastWeek} novo(s) nos últimos 7 dias` : ''}</span></section>
    {(data.sources ?? []).some((source) => source.status === 'failed' || source.status === 'partial') && <section className="source-status" aria-label="Estado das fontes"><strong>Fontes com acesso incompleto</strong><ul>{data.sources?.filter((source) => source.status === 'failed' || source.status === 'partial').map((source) => <li key={source.source_id}><span>{source.name}: {source.status === 'failed' ? 'indisponível' : 'parcial'}</span>{source.error && <small>{source.error}</small>}</li>)}</ul></section>}
    <section className="list-section"><div className="section-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> OPORTUNIDADES</div><h2>Imóveis em <em>destaque</em></h2></div><span className="result-count">{filtered.length} de {properties.length} imóveis</span></div>
      <div className="filters">
        <label className="search"><Search size={17} /><input aria-label="Buscar imóvel" placeholder="Buscar endereço ou bairro" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label className="select-wrap"><select aria-label="Filtrar status do leilão" value={statusScope} onChange={(event) => setStatusScope(event.target.value)}><option value="new">Novos · últimos 7 dias</option><option value="active">Somente ativos</option><option value="opportunities">Ativos e próximos</option><option value="all">Todos os anúncios</option></select></label>
        <label className="select-wrap"><SlidersHorizontal size={15} /><select aria-label="Filtrar cidade" value={city} onChange={(event) => setCity(event.target.value)}><option>Todas as cidades</option>{cities.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="select-wrap"><Filter size={15} /><select aria-label="Filtrar tipo" value={type} onChange={(event) => setType(event.target.value)}><option>Todos os tipos</option>{types.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="select-wrap"><select aria-label="Filtrar categoria" value={category} onChange={(event) => setCategory(event.target.value)}><option value="Todas">Categorias A/B</option><option value="A">A · Prioritária</option><option value="B">B · Demais</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar ocupação" value={occupancy} onChange={(event) => setOccupancy(event.target.value)}><option value="Todas">Todas ocupações</option><option value="ocupad">Ocupado</option><option value="desocupado">Desocupado</option><option value="Desconhecida">Desconhecida</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar riscos" value={risk} onChange={(event) => setRisk(event.target.value)}><option value="Todos">Todos os riscos</option><option value="Com alertas">Com alertas</option><option value="Sem alertas">Sem alertas</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar data do leilão" value={dateWindow} onChange={(event) => setDateWindow(event.target.value)}><option value="Todas">Todas as datas</option><option value="30">Próximos 30 dias</option><option value="60">Próximos 60 dias</option><option value="180">Próximos 180 dias</option></select></label>
        <label className="number-filter">Preço mín. <input aria-label="Preço mínimo" type="number" min="0" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} /></label>
        <label className="number-filter">Preço máx. <input aria-label="Preço máximo" type="number" min="0" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} /></label>
        <label className="number-filter">Desconto mín. % <input aria-label="Desconto mínimo" type="number" min="0" max="100" value={minDiscount} onChange={(event) => setMinDiscount(event.target.value)} /></label>
      </div>
      {filtered.length ? <div className="cards">{filtered.map((item) => {
        const priority = item.classification === 'A';
        const isNew = isRecentNew(item);
        const nextEvent = auctionEvent(item, today);
        const currentStatus = displayStatus(item, today);
        const statusLabels: Record<string, string> = { active: item.validation_status === 'verified' ? 'ATIVO · OFICIAL' : 'ATIVO · CONFIRME NO PORTAL', scheduled_unverified: 'PRÓXIMO · CONFIRMAR', ended_unverified: 'DATA PASSADA · CONFIRMAR', closed: 'ENCERRADO', cancelled: 'CANCELADO', sold: 'VENDIDO', suspended: 'SUSPENSO', unknown: 'SITUAÇÃO DESCONHECIDA' };
        const listingUrl = item.official_url || item.source_listing_url;
        const linkLabel = item.official_url ? 'Anúncio oficial' : item.source_listing_url ? 'Ver anúncio · não verificado' : 'URL oficial não confirmada';
        return <article className={`property${isNew ? ' property-new' : ''}`} key={item.id}><div className="property-top"><span className="property-type">{item.property_type || 'Imóvel'} <span>·</span> {item.city}/{item.state}</span><div className="property-badges">{isNew && <span className="new-badge">NOVO</span>}{priority && <span className="badge"><ArrowDownRight size={13} /> PRIORIDADE</span>}<span className={`status-badge status-${currentStatus}`}>{statusLabels[currentStatus] ?? 'SITUAÇÃO DESCONHECIDA'}</span></div></div><PropertyPhoto property={item} /><h3>{item.address || `${item.property_type || 'Imóvel'} em ${item.city}`}</h3><div className="property-location"><span>BAIRRO</span><strong>{item.neighborhood || 'Não informado pela fonte'}</strong><span className="occupancy">{item.occupancy ? `OCUPAÇÃO · ${item.occupancy}` : 'OCUPAÇÃO · desconhecida'}</span></div><div className="auction-date"><span>DATA DO LEILÃO</span><strong>{nextEvent?.date ? date(nextEvent.date) : 'Não informada'}</strong>{nextEvent?.time && <small>{nextEvent.time}</small>}</div><div className="property-metrics"><div><span>1ª PRAÇA</span><strong>{money(item.first_minimum_bid_brl)}</strong></div><div><span>2ª PRAÇA</span><strong>{money(item.second_minimum_bid_brl)}</strong></div><div><span>{item.current_minimum_bid_brl != null ? 'LANCE ATUAL' : 'PREÇO EXIBIDO NA FONTE'}</span><strong>{money(item.current_minimum_bid_brl ?? item.source_listing_price_brl)}</strong></div><div><span>DESCONTO S/ AVALIAÇÃO</span><strong>{item.discount_on_appraisal_percent != null ? `${item.discount_on_appraisal_percent}%` : 'Não informado pela fonte'} {item.discount_on_appraisal_percent != null && <ArrowDownRight size={14} />}</strong></div><div><span>ÁREA PRIVATIVA</span><strong>{item.area_privative_m2 ? `${item.area_privative_m2} m²` : '—'}</strong></div></div><div className="property-bottom"><span>{item.auctioneer || 'Leiloeiro não informado'} · Categoria {item.classification ?? 'B'}</span>{listingUrl ? <a href={listingUrl} target="_blank" rel="noreferrer">{linkLabel} <ArrowUpRight size={15} /></a> : <span>{linkLabel}</span>}</div></article>;
      })}</div> : <div className="empty"><div className="empty-icon"><Search size={20} /></div><h3>{loading ? 'Buscando oportunidades…' : statusScope === 'new' ? 'Nenhum imóvel novo nos últimos 7 dias.' : properties.length === 0 ? 'Ainda não há anúncios confirmados.' : 'Nenhum imóvel corresponde aos filtros.'}</h3><p>{statusScope === 'new' && properties.length ? 'Não há novas descobertas recentes. Os anúncios anteriores continuam preservados; selecione “Somente ativos” para consultar a lista completa.' : properties.length === 0 ? 'O painel não inclui anúncios fictícios. Fontes bloqueadas ou indisponíveis aparecem no relatório da coleta.' : 'Ajuste os filtros para ver outros resultados.'}</p>{properties.length === 0 && <a href="https://www.portalzuk.com.br/leilao-de-imoveis/u/todos-imoveis/sc" target="_blank" rel="noreferrer">Consultar oportunidades oficiais <ExternalLink size={14} /></a>}</div>}
    </section>
    <footer><span>RADAR DE LEILÕES <span className="footer-sep">/</span> MONITOR</span><p>Dados de anúncios públicos. Confirme as informações no anúncio, edital e documentos oficiais antes de qualquer decisão.</p><span>Informação para análise, não parecer jurídico.</span></footer>
  </main>;
}
