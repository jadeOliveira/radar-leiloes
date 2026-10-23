import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ExternalLink, Filter, House, Search, SlidersHorizontal, Star, X } from 'lucide-react';
import monitorConfig from '../config/monitor.json';

type AuctionEvent = { date?: string; time?: string | null; minimum_bid_brl?: number | null; stage?: string };
type Property = {
  id: string; city: string; state: string; address?: string | null; neighborhood?: string | null;
  source_ids?: string[]; provenance?: { source_id?: string };
  property_type?: string | null; auctioneer?: string | null; official_url?: string | null;
  source_listing_url?: string | null; validation_status?: string | null;
  image_urls?: string[];
  first_minimum_bid_brl?: number | null; second_minimum_bid_brl?: number | null;
  current_minimum_bid_brl?: number | null; source_listing_price_brl?: number | null; appraisal_value_brl?: number | null;
  discount_on_appraisal_percent?: number | null; area_privative_m2?: number | null;
  occupancy?: string | null; status?: string; classification?: 'A' | 'B'; risk_flags?: string[];
  auction_events?: AuctionEvent[]; first_seen_at?: string | null; last_checked_at?: string | null;
  newly_discovered_at?: string | null; title?: string | null;
};
type SourceStatus = { source_id: string; name: string; status: string; last_success_at?: string; error?: string };
type ConfiguredSource = { id: string; name: string; enabled?: boolean; url: string };
type Dataset = { updated_at?: string | null; cities?: string[]; priority?: { max_bid_brl?: number; min_discount_percent?: number }; sources?: SourceStatus[]; properties?: Property[] };
type ChangeEntry = { property_id: string; detected_at?: string; changes?: Array<{ field?: string; before?: unknown; after?: unknown }> };
type ChangeLog = { runs?: Array<{ detected_at?: string; changes?: ChangeEntry[] }> };
type RunReport = { status?: string; started_at?: string; finished_at?: string; data_status?: 'updated' | 'unchanged' | 'unavailable'; data_updated_at?: string | null; new_property_ids?: string[]; counts?: { new_listings?: number; changed_listings?: number; sources_succeeded?: number; sources_partial?: number; sources_failed?: number }; sources?: SourceStatus[] };
const favoritesStorageKey = 'radar-leiloes:favorites:v1';
const readFavorites = (): string[] => {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(favoritesStorageKey) ?? '[]');
    return Array.isArray(saved) ? [...new Set(saved.filter((id): id is string => typeof id === 'string'))] : [];
  } catch {
    return [];
  }
};
const money = (value?: number | null) => value == null ? 'Não informado' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value);
const date = (value?: string | null) => {
  if (!value) return '—';
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const parsed = dateOnly ? new Date(Date.UTC(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]), 12)) : new Date(value);
  return parsed.toLocaleDateString('pt-BR', { timeZone: dateOnly ? 'UTC' : 'America/Sao_Paulo' });
};
const brazilToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const configuredSources = monitorConfig.sources as ConfiguredSource[];
const sourceCitySlug = (city: string) => city.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const sourceUrl = (url: string) => url.replaceAll('{page}', '1').replaceAll('{city_slug}', sourceCitySlug(monitorConfig.cities[0] ?? ''));
const saoPauloDate = (timestamp?: string | null) => timestamp ? new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date(timestamp)) : null;
const discoveryDate = (property: Property) => saoPauloDate(property.newly_discovered_at ?? property.first_seen_at);
const isDiscoveredOn = (property: Property, day: string) => discoveryDate(property) === day;
const isNewToday = (property: Property, today: string) => isDiscoveredOn(property, today);
const hasChangesOn = (changeLog: ChangeLog, propertyId: string, day: string) => (changeLog.runs ?? []).some((run) =>
  (run.changes ?? []).some((entry) => {
    const detected = entry.detected_at ?? run.detected_at;
    const hasRealChange = (entry.changes ?? []).some((change) => !(change.field === 'record' && change.after === 'new'));
    return entry.property_id === propertyId && Boolean(detected) && saoPauloDate(detected) === day && hasRealChange;
  }),
);
const futureAuctionDate = (property: Property, today: string) => property.auction_events?.map((event) => event.date).filter((value): value is string => typeof value === 'string' && value >= today).sort()[0];
const auctionEvent = (property: Property, today: string) => {
  const events = [...(property.auction_events ?? [])].filter((event) => event.date).sort((left, right) => (left.date ?? '').localeCompare(right.date ?? ''));
  return events.find((event) => (event.date ?? '') >= today) ?? events.at(-1);
};
const displayStatus = (property: Property, today: string) => property.status === 'unknown' && futureAuctionDate(property, today) ? 'scheduled_unverified' : property.status ?? 'unknown';
const isRealEstate = (property: Property) => {
  const type = (property.property_type ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').trim();
  return ['casa', 'apartamento', 'terreno', 'galpao', 'galpao industrial'].includes(type);
};

function PropertyPhoto({ property }: { property: Property }) {
  const [attempt, setAttempt] = useState(0);
  useEffect(() => setAttempt(0), [property.id, property.image_urls]);
  const image = property.image_urls?.[attempt];
  if (!image) return <div className="property-image-placeholder"><House size={22} /><span>Foto não disponível na fonte</span></div>;
  return <img key={image} className="property-image" src={image} alt={`Foto do imóvel em ${property.city}`} loading="lazy" referrerPolicy="no-referrer" onError={() => setAttempt((current) => current + 1)} />;
}

export default function App() {
  const [data, setData] = useState<Dataset>({ properties: [] });
  const [lastRun, setLastRun] = useState<RunReport>({});
  const [changeLog, setChangeLog] = useState<ChangeLog>({});
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('Todas as cidades');
  const [type, setType] = useState('Todos os tipos');
  const [category, setCategory] = useState('Todas');
  const [occupancy, setOccupancy] = useState('Todas');
  const [risk, setRisk] = useState('Todos');
  const [dateWindow, setDateWindow] = useState('Todas');
  const [statusScope, setStatusScope] = useState('new');
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false);
  const [favoriteIds, setFavoriteIds] = useState<string[]>(readFavorites);
  const [favoritesStorageError, setFavoritesStorageError] = useState(false);
  const toggleFavorite = (id: string) => {
    const next = favoriteIds.includes(id) ? favoriteIds.filter((favoriteId) => favoriteId !== id) : [...favoriteIds, id];
    setFavoriteIds(next);
    try {
      localStorage.setItem(favoritesStorageKey, JSON.stringify(next));
      setFavoritesStorageError(false);
    } catch {
      setFavoritesStorageError(true);
    }
  };
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');
  const [minDiscount, setMinDiscount] = useState('');
  const [loading, setLoading] = useState(true);
  const [sourceDetailsOpen, setSourceDetailsOpen] = useState(false);
  const sourceDetailsDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const load = (name: string) => fetch(`${import.meta.env.BASE_URL}data/${name}`, { cache: 'no-store' }).then((response) => response.ok ? response.json() : {});
    Promise.all([load('properties.json'), load('last-run.json'), load('changes.json')])
      .then(([properties, run, changes]) => { const propertyData = properties as Dataset; const runData = run as RunReport; setData({ ...propertyData, sources: runData.sources ?? propertyData.sources }); setLastRun(runData); setChangeLog(changes as ChangeLog); })
      .catch(() => setData({ properties: [] }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const dialog = sourceDetailsDialog.current;
    if (!dialog) return;
    if (sourceDetailsOpen && !dialog.open) dialog.showModal();
    if (!sourceDetailsOpen && dialog.open) dialog.close();
    if (!sourceDetailsOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, [sourceDetailsOpen]);

  // Hide legacy vehicle/movable-goods records without deleting stored history.
  const properties = (data.properties ?? []).filter(isRealEstate);
  const sourceNameById = new Map((data.sources ?? []).map((source) => [source.source_id, source.name] as const));
  const sourceLabels: Record<string, string> = { muller_leiloes: 'Müller Leilões', mazzolli: 'Mazzolli Leilões', imoveisfaixa: 'ImóveisFaixa', nucleo: 'Núcleo Leilões', leilaoimovel: 'Leilão Imóvel' };
  const cities = data.cities?.length ? data.cities : [...new Set(properties.map((item) => item.city).filter(Boolean))].sort();
  const types = [...new Set(properties.map((item) => item.property_type).filter(Boolean))].sort() as string[];
  const filtered = useMemo(() => {
    const today = brazilToday();
    const matchesScope = (item: Property) => {
      const status = displayStatus(item, today);
      if (statusScope === 'new') return isNewToday(item, today);
      if (statusScope === 'favorites') return favoriteIds.includes(item.id);
      if (statusScope === 'all') return true;
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
  }, [properties, changeLog, query, city, type, category, occupancy, risk, dateWindow, minPrice, maxPrice, minDiscount, statusScope, favoriteIds]);
  const today = brazilToday();
  const activeCount = properties.filter((item) => displayStatus(item, today) === 'active').length;
  const lastDataUpdate = data.updated_at ? new Date(data.updated_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }) : 'Sem anúncios';
  const sourceStatusById = new Map((data.sources ?? []).map((source) => [source.source_id, source] as const));
  const incompleteSources = (data.sources ?? []).filter((source) => source.status === 'failed' || source.status === 'partial');
  const newTodayCount = properties.filter((item) => isDiscoveredOn(item, today)).length;
  const changedTodayCount = properties.filter((item) => !isNewToday(item, today) && hasChangesOn(changeLog, item.id, today)).length;
  const lastRunTime = lastRun.finished_at ? new Date(lastRun.finished_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }) : 'indisponível';
  const favoriteCount = properties.filter((item) => favoriteIds.includes(item.id)).length;
  const extraFilterCount = [category !== 'Todas', occupancy !== 'Todas', risk !== 'Todos', dateWindow !== 'Todas', minPrice !== '', maxPrice !== '', minDiscount !== ''].filter(Boolean).length;
  const dataStatusText = loading ? 'Carregando anúncios…'
    : lastRun.data_status === 'unavailable' ? 'Coleta indisponível; anúncios anteriores preservados'
    : !lastRun.finished_at ? 'Aguardando o relatório da coleta'
    : `${newTodayCount} ${newTodayCount === 1 ? 'novo imóvel' : 'novos imóveis'} hoje`;

  return <main className="page">
    <header className="topbar"><a className="brand" href="#top"><span className="brand-mark"><House size={19} /></span><span>RADAR<span className="brand-light"> DE LEILÕES</span></span></a><div className="topbar-right"><button className="sources-nav" type="button" aria-haspopup="dialog" aria-controls="sources-dialog" onClick={() => setSourceDetailsOpen(true)}>Fontes monitoradas</button><span className="top-note">SANTA CATARINA <i /> MONITORAMENTO DIÁRIO</span></div></header>
    <section className="compact-header" id="top">
      <div><h1>Imóveis em <em>leilão</em></h1><p>{cities.length} cidades em Santa Catarina · anúncios públicos</p></div>
      <div className="collection-time"><span>Última coleta</span><strong>{lastRunTime}</strong></div>
    </section>
    <section className={`freshness-banner compact-update freshness-${lastRun.data_status ?? 'unknown'}`} aria-live="polite"><strong>{dataStatusText}</strong><span>{changedTodayCount > 0 ? `${changedTodayCount} ${changedTodayCount === 1 ? 'anúncio conhecido alterado' : 'anúncios conhecidos alterados'}` : 'Nenhuma alteração em anúncios conhecidos'}</span></section>
    <dialog className="source-details-dialog" id="sources-dialog" ref={sourceDetailsDialog} aria-labelledby="source-details-title" aria-describedby="source-details-intro" onClose={() => setSourceDetailsOpen(false)}>
      <div className="source-dialog-header">
        <div><div className="eyebrow"><span className="eyebrow-line" /> TRANSPARÊNCIA</div><h2 id="source-details-title">Fontes <em>monitoradas</em></h2></div>
        <button className="source-dialog-close" type="button" aria-label="Fechar fontes monitoradas" autoFocus onClick={() => setSourceDetailsOpen(false)}><X size={18} /></button>
      </div>
      <p id="source-details-intro" className="sources-intro">Os portais consultados pelo monitor e o resultado do relatório mais recente. Acesso parcial ou indisponível não significa que o site esteja permanentemente fora do ar.</p>
      <div className="sources-summary"><span>{configuredSources.filter((source) => source.enabled !== false).length} fontes configuradas</span><span>Relatório: {lastRunTime}</span><span>Dados dos anúncios: {lastDataUpdate}</span>{incompleteSources.length > 0 && <strong>{incompleteSources.length} fontes com acesso incompleto</strong>}</div>
      <div className="sources-grid">{configuredSources.map((source) => {
        const latest = sourceStatusById.get(source.id);
        const status = source.enabled === false ? 'disabled' : latest?.status ?? 'unknown';
        const statusLabel = status === 'success' ? 'Consultada' : status === 'partial' ? 'Parcial' : status === 'failed' ? 'Indisponível nesta coleta' : status === 'disabled' ? 'Desativada' : 'Sem relatório';
        return <article className="source-card" key={source.id}><div className="source-card-top"><h3>{source.name}</h3><span className={`source-state source-state-${status}`}>{statusLabel}</span></div>{latest?.error && <p className="source-card-error">{latest.error}</p>}<a href={sourceUrl(source.url)} target="_blank" rel="noreferrer">Abrir site <ExternalLink size={13} /></a></article>;
      })}</div>
      <p className="sources-note">Anúncios de agregadores, como a Hasta, permanecem identificados como não verificados até a conferência na página original do leiloeiro.</p>
    </dialog>
    <section className="list-section compact-list" aria-label="Anúncios de imóveis">
      <nav className="listing-scopes" aria-label="Filtrar anúncios">
        <button type="button" aria-pressed={statusScope === 'new'} onClick={() => setStatusScope('new')}>Novos <small>{newTodayCount}</small></button>
        <button type="button" aria-pressed={statusScope === 'active'} onClick={() => setStatusScope('active')}>Ativos <small>{activeCount}</small></button>
        <button type="button" aria-pressed={statusScope === 'all'} onClick={() => setStatusScope('all')}>Todos <small>{properties.length}</small></button>
        <button type="button" aria-pressed={statusScope === 'favorites'} onClick={() => setStatusScope('favorites')}><Star size={14} /> Favoritos <small>{favoriteCount}</small></button>
        <span className="scope-result-count" aria-live="polite">{filtered.length} de {properties.length} imóveis</span>
      </nav>
      <div className="filters">
        <label className="search"><Search size={17} /><input aria-label="Buscar imóvel" placeholder="Buscar endereço ou bairro" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label className="select-wrap"><SlidersHorizontal size={15} /><select aria-label="Filtrar cidade" value={city} onChange={(event) => setCity(event.target.value)}><option>Todas as cidades</option>{cities.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="select-wrap"><Filter size={15} /><select aria-label="Filtrar tipo" value={type} onChange={(event) => setType(event.target.value)}><option>Todos os tipos</option>{types.map((item) => <option key={item}>{item}</option>)}</select></label>
        <button className="more-filters-button" type="button" aria-expanded={moreFiltersOpen} aria-controls="advanced-filters" onClick={() => setMoreFiltersOpen(!moreFiltersOpen)}><SlidersHorizontal size={15} /> Mais filtros{extraFilterCount > 0 ? ` (${extraFilterCount})` : ''}</button>
      </div>
      <div className="filters advanced-filters" id="advanced-filters" hidden={!moreFiltersOpen}>
        <label className="select-wrap"><select aria-label="Filtrar categoria" value={category} onChange={(event) => setCategory(event.target.value)}><option value="Todas">Categorias A/B</option><option value="A">A · Prioritária</option><option value="B">B · Demais</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar ocupação" value={occupancy} onChange={(event) => setOccupancy(event.target.value)}><option value="Todas">Todas ocupações</option><option value="ocupad">Ocupado</option><option value="desocupado">Desocupado</option><option value="Desconhecida">Desconhecida</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar riscos" value={risk} onChange={(event) => setRisk(event.target.value)}><option value="Todos">Todos os riscos</option><option value="Com alertas">Com alertas</option><option value="Sem alertas">Sem alertas</option></select></label>
        <label className="select-wrap"><select aria-label="Filtrar data do leilão" value={dateWindow} onChange={(event) => setDateWindow(event.target.value)}><option value="Todas">Todas as datas</option><option value="30">Próximos 30 dias</option><option value="60">Próximos 60 dias</option><option value="180">Próximos 180 dias</option></select></label>
        <label className="number-filter">Preço mín. <input aria-label="Preço mínimo" type="number" min="0" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} /></label>
        <label className="number-filter">Preço máx. <input aria-label="Preço máximo" type="number" min="0" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} /></label>
        <label className="number-filter">Desconto mín. % <input aria-label="Desconto mínimo" type="number" min="0" max="100" value={minDiscount} onChange={(event) => setMinDiscount(event.target.value)} /></label>
      </div>
      {statusScope === 'favorites' && <p className="favorites-note">Seus favoritos ficam salvos neste navegador. Os demais filtros também se aplicam.</p>}
      {favoritesStorageError && <p className="favorites-warning" role="status">Não foi possível salvar no navegador. Seus favoritos ficam disponíveis somente enquanto esta página estiver aberta.</p>}
      {filtered.length ? <div className="cards">{filtered.map((item) => {
        const priority = item.classification === 'A';
        const isNew = isNewToday(item, today);
        const isChanged = hasChangesOn(changeLog, item.id, today);
        const nextEvent = auctionEvent(item, today);
        const currentStatus = displayStatus(item, today);
        const statusLabels: Record<string, string> = { active: item.validation_status === 'verified' ? 'ATIVO · OFICIAL' : 'ATIVO · CONFIRME NO PORTAL', scheduled_unverified: 'PRÓXIMO · CONFIRMAR', ended_unverified: 'DATA PASSADA · CONFIRMAR', closed: 'ENCERRADO', cancelled: 'CANCELADO', sold: 'VENDIDO', suspended: 'SUSPENSO', unknown: 'SITUAÇÃO DESCONHECIDA' };
        const listingUrl = item.official_url || item.source_listing_url;
        const linkLabel = item.official_url ? 'Anúncio oficial' : item.source_listing_url ? 'Ver anúncio · não verificado' : 'URL oficial não confirmada';
        const sourceIds = item.source_ids?.length ? item.source_ids : item.provenance?.source_id ? [item.provenance.source_id] : [];
        const propertySources = sourceIds.map((sourceId) => sourceNameById.get(sourceId) ?? sourceLabels[sourceId] ?? sourceId);
        return <article className={`property${isNew ? ' property-new' : ''}`} key={item.id}><div className="property-top"><span className="property-type">{item.property_type || 'Imóvel'} <span>·</span> {item.city}/{item.state}</span><div className="property-badges">{isNew ? <span className="new-badge">NOVO</span> : isChanged ? <span className="new-badge">ALTERADO</span> : null}{priority && <span className="badge"><ArrowDownRight size={13} /> PRIORIDADE</span>}<span className={`status-badge status-${currentStatus}`}>{statusLabels[currentStatus] ?? 'SITUAÇÃO DESCONHECIDA'}</span></div></div><div className="property-photo"><PropertyPhoto property={item} /><button className={`favorite-button${favoriteIds.includes(item.id) ? ' is-favorite' : ''}`} type="button" aria-pressed={favoriteIds.includes(item.id)} aria-label={favoriteIds.includes(item.id) ? 'Remover dos favoritos' : 'Adicionar aos favoritos'} title={favoriteIds.includes(item.id) ? 'Remover dos favoritos' : 'Adicionar aos favoritos'} onClick={() => toggleFavorite(item.id)}><Star size={20} fill={favoriteIds.includes(item.id) ? 'currentColor' : 'none'} /></button></div><h3>{item.title || `${item.property_type || 'Imóvel'} em ${item.city}`}</h3><div className="property-location"><span>ENDEREÇO</span><strong>{item.address || 'Não informado pela fonte'}</strong><span>BAIRRO</span><strong>{item.neighborhood || 'Não informado pela fonte'}</strong><span className="occupancy">{item.occupancy ? `OCUPAÇÃO · ${item.occupancy}` : 'OCUPAÇÃO · desconhecida'}</span></div><div className="auction-date"><span>DATA DO LEILÃO</span><strong>{nextEvent?.date ? date(nextEvent.date) : 'Não informada'}</strong>{nextEvent?.time && <small>{nextEvent.time}</small>}</div><div className="property-sources"><span>FONTE DA BUSCA</span><div className="property-source-list">{propertySources.length ? propertySources.map((name) => <span className="source-tag" key={name}>{name}</span>) : <span className="source-unknown">Não informada</span>}</div></div><div className="property-metrics"><div><span>1ª PRAÇA</span><strong>{money(item.first_minimum_bid_brl)}</strong></div><div><span>2ª PRAÇA</span><strong>{money(item.second_minimum_bid_brl)}</strong></div><div><span>{item.current_minimum_bid_brl != null ? 'LANCE ATUAL' : 'PREÇO EXIBIDO NA FONTE'}</span><strong>{money(item.current_minimum_bid_brl ?? item.source_listing_price_brl)}</strong></div><div><span>DESCONTO S/ AVALIAÇÃO</span><strong>{item.discount_on_appraisal_percent != null ? `${item.discount_on_appraisal_percent}%` : 'Não informado pela fonte'} {item.discount_on_appraisal_percent != null && <ArrowDownRight size={14} />}</strong></div>{item.appraisal_value_brl != null && <div><span>VALOR DE AVALIAÇÃO</span><strong>{money(item.appraisal_value_brl)}</strong></div>}<div><span>ÁREA PRIVATIVA</span><strong>{item.area_privative_m2 ? `${item.area_privative_m2} m²` : '—'}</strong></div></div><div className="property-bottom"><span>{item.auctioneer || 'Leiloeiro não informado'} · Categoria {item.classification ?? 'B'}</span>{listingUrl ? <a href={listingUrl} target="_blank" rel="noreferrer">{linkLabel} <ArrowUpRight size={15} /></a> : <span>{linkLabel}</span>}</div></article>;
      })}</div> : <div className="empty"><div className="empty-icon"><Search size={20} /></div><h3>{loading ? 'Buscando oportunidades…' : statusScope === 'new' ? 'Nenhum imóvel novo identificado hoje.' : statusScope === 'favorites' ? 'Nenhum favorito encontrado.' : statusScope === 'active' ? 'Nenhum imóvel ativo.' : properties.length === 0 ? 'Ainda não há anúncios confirmados.' : 'Nenhum imóvel corresponde aos filtros.'}</h3><p>{statusScope === 'favorites' ? 'Clique na estrela de um anúncio para salvá-lo aqui. Se você já marcou favoritos, ajuste os demais filtros para encontrá-los.' : statusScope === 'new' && properties.length ? 'Novos mostra somente os imóveis identificados hoje. Amanhã eles ficam disponíveis no filtro “Todos”.' : properties.length === 0 ? 'O painel não inclui anúncios fictícios. Fontes bloqueadas ou indisponíveis aparecem no relatório da coleta.' : 'Ajuste os filtros para ver outros resultados.'}</p>{properties.length === 0 && <a href="https://www.portalzuk.com.br/leilao-de-imoveis/u/todos-imoveis/sc" target="_blank" rel="noreferrer">Consultar oportunidades oficiais <ExternalLink size={14} /></a>}</div>}
    </section>
    <footer><span>RADAR DE LEILÕES <span className="footer-sep">/</span> MONITOR</span><p>Dados de anúncios públicos. Confirme as informações no anúncio, edital e documentos oficiais antes de qualquer decisão.</p><span>Informação para análise, não parecer jurídico.</span></footer>
  </main>;
}
