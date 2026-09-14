import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Check, ChevronLeft, ChevronRight, Handshake, MapPin, Search, ShieldCheck, Sparkles, Tag, Users, X} from 'lucide-react';
import {Link, useSearchParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import ProductCard from '../components/ProductCard';
import PartnerAdSpot from '../components/PartnerAdSpot';

const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const rows = [
  {label:'Publicação normal no marketplace', values:[true,true,true]},
  {label:'Validade da publicação/plano', values:['7 dias','15 dias','30 dias']},
  {label:'Limite do plano Grátis', values:['1 anúncio por conta','Sem limite de contratações','Sem limite de contratações']},
  {label:'Selo de anúncio em destaque', values:[false,true,true]},
  {label:'Prioridade nas buscas', values:['Sem prioridade','Maior','Máxima']},
  {label:'Tempo em evidência', values:['Sem destaque','15 dias','30 dias']},
  {label:'Melhor posição no catálogo', values:[false,true,true]},
  {label:'Mais visualizações no catálogo', values:[false,false,true]},
  {label:'Maior exposição entre anúncios', values:[false,false,true]},
  {label:'Vitrine de parceiros', values:['Não','Rotativa','Prioridade']},
  {label:'Slider principal da Home', values:[false,false,true]},
];

function tierClass(index,total){
  if(index===0) return 'basic';
  if(index===total-1) return 'premium';
  return 'plus';
}

function renderCell(value){
  if(value===true) return <span className="table-yes"><Check size={15}/> Sim</span>;
  if(value===false) return <span className="table-no"><X size={15}/> Não</span>;
  return <span className="table-text">{value}</span>;
}

export default function Home(){
 const [searchParams,setSearchParams]=useSearchParams();
 const [products,setProducts]=useState([]);
 const [categories,setCategories]=useState([]);
 const [stats,setStats]=useState({products:0,sellers:0,cities:0});
 const [plans,setPlans]=useState([]);
 const [partnerTop,setPartnerTop]=useState([]);
 const [partnerEnd,setPartnerEnd]=useState([]);
 const [heroSlide,setHeroSlide]=useState(0);
 const [q,setQ]=useState(searchParams.get('q')||'');
 const [cat,setCat]=useState(searchParams.get('category')||'');
 const [sort,setSort]=useState('newest');
 const [city,setCity]=useState(searchParams.get('city')||'');
 const [neighborhood,setNeighborhood]=useState(searchParams.get('neighborhood')||'');
 const [offset,setOffset]=useState(0);
 const [hasMore,setHasMore]=useState(true);
 const [loadingProducts,setLoadingProducts]=useState(false);
 const feedEndRef=useRef(null);
 const PAGE_SIZE=12;

 const productsUrl=(start=0)=>`/api/products?search=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}&city=${encodeURIComponent(city)}&neighborhood=${encodeURIComponent(neighborhood)}&sort=${sort}&limit=${PAGE_SIZE}&offset=${start}`;

 useEffect(()=>{
   api('/api/categories').then(setCategories);
   api('/api/public/stats').then(setStats).catch(()=>{});
   api('/api/plans').then(setPlans).catch(()=>setPlans([]));
   api('/api/partner-ads?slot=home_top&limit=1').then(setPartnerTop).catch(()=>setPartnerTop([]));
   api('/api/partner-ads?slot=feed_end&limit=3').then(setPartnerEnd).catch(()=>setPartnerEnd([]));
 },[]);

 useEffect(()=>{
   const nextQ=searchParams.get('q')||'';
   const nextCity=searchParams.get('city')||'';
   const nextNeighborhood=searchParams.get('neighborhood')||'';
   const nextCategory=searchParams.get('category')||'';
   setQ(nextQ); setCity(nextCity); setNeighborhood(nextNeighborhood); setCat(nextCategory);
 },[searchParams]);

 useEffect(()=>{
   let active=true;
   const t=setTimeout(async()=>{
     setLoadingProducts(true);
     try{
       const data=await api(productsUrl(0));
       if(!active) return;
       setProducts(data||[]);
       setOffset((data||[]).length);
       setHasMore((data||[]).length===PAGE_SIZE);
     }catch{
       if(active){setProducts([]);setOffset(0);setHasMore(false)}
     }finally{if(active)setLoadingProducts(false)}
   },250);
   return()=>{active=false;clearTimeout(t)};
 },[q,cat,sort,city,neighborhood]);

 async function loadMore(){
   if(loadingProducts||!hasMore) return;
   setLoadingProducts(true);
   try{
     const data=await api(productsUrl(offset));
     const next=data||[];
     setProducts(prev=>{
       const seen=new Set(prev.map(x=>x.id));
       return [...prev,...next.filter(x=>!seen.has(x.id))];
     });
     setOffset(prev=>prev+next.length);
     setHasMore(next.length===PAGE_SIZE);
   }catch{setHasMore(false)}finally{setLoadingProducts(false)}
 }

 useEffect(()=>{
   const node=feedEndRef.current;
   if(!node||!hasMore) return;
   const observer=new IntersectionObserver(entries=>{if(entries[0]?.isIntersecting) loadMore()},{rootMargin:'500px 0px'});
   observer.observe(node);
   return()=>observer.disconnect();
 },[offset,hasMore,loadingProducts,q,cat,sort,city,neighborhood]);

 function submitSearch(e){
   e?.preventDefault?.();
   const p=new URLSearchParams();
   if(q.trim()) p.set('q',q.trim());
   if(city.trim()) p.set('city',city.trim());
   if(neighborhood.trim()) p.set('neighborhood',neighborhood.trim());
   if(cat) p.set('category',cat);
   setSearchParams(p);
 }

 function chooseCategory(slug){
   const next=cat===slug?'':slug;
   setCat(next);
   const p=new URLSearchParams(searchParams);
   if(next) p.set('category',next); else p.delete('category');
   setSearchParams(p);
 }

 const featured=useMemo(()=>products.filter(p=>p.featured_active).slice(0,4),[products]);
 const heroSlides=useMemo(()=>products.filter(p=>p.featured_active && Number(p.boost_level||0)>=3 && ((p.images&&p.images[0])||p.image_url)).slice(0,6),[products]);
 const activeHeroSlide=heroSlides[heroSlide]||heroSlides[0]||null;

 useEffect(()=>{
   if(!heroSlides.length){setHeroSlide(0);return}
   if(heroSlide>=heroSlides.length) setHeroSlide(0);
 },[heroSlides.length,heroSlide]);

 useEffect(()=>{
   if(heroSlides.length<2) return;
   const timer=setInterval(()=>setHeroSlide(i=>(i+1)%heroSlides.length),4500);
   return()=>clearInterval(timer);
 },[heroSlides.length]);

 function moveHeroSlide(step){
   if(!heroSlides.length) return;
   setHeroSlide(i=>(i+step+heroSlides.length)%heroSlides.length);
 }

 return <>
  <section className="market-hero">
    <div className="market-hero-copy">
      <span className="eyebrow">COMPRE E VENDA PERTO DE VOCÊ</span>
      <h1>Seu marketplace local, simples e direto.</h1>
      <p>Publique produtos, converse com compradores e negocie de forma organizada em um só lugar.</p>

      <form className="market-search" onSubmit={submitSearch}>
        <div className="market-search-main"><Search/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="O que você está procurando?"/></div>
        <button type="submit">Buscar</button>
      </form>
      <div className="market-location-row">
        <label><MapPin/><input value={city} onChange={e=>setCity(e.target.value)} placeholder="Cidade"/></label>
        <label><input value={neighborhood} onChange={e=>setNeighborhood(e.target.value)} placeholder="Bairro"/></label>
      </div>

      <div className="market-benefits">
        <div><ShieldCheck/><span><b>Vendedores verificados</b><small>Mais segurança</small></span></div>
        <div><Tag/><span><b>Venda direta</b><small>Sem intermediários</small></span></div>
        <div><Sparkles/><span><b>Anúncios em destaque</b><small>Mais visibilidade</small></span></div>
        <div><Users/><span><b>Marketplace local</b><small>Na sua região</small></span></div>
      </div>

      <div className="market-stats" aria-label="Estatísticas do marketplace">
        <span><b>{stats.products}</b> anúncios</span>
        <span><b>{stats.sellers}</b> usuários</span>
        <span><b>{stats.cities}</b> cidades</span>
      </div>
    </div>

    <div className="market-hero-visual hero-slider-visual">
      <div className="hero-orb hero-orb-one"/><div className="hero-orb hero-orb-two"/>
      <div className="hero-slider-heading">
        <span>EM ALTA AGORA</span>
        <b>Veja o que acabou de chegar</b>
      </div>

      {activeHeroSlide ? <div className="hero-live-slider">
        <Link className="hero-live-slide" to={`/produto/${activeHeroSlide.id}`}>
          <img
            src={imageUrl((activeHeroSlide.images&&activeHeroSlide.images[0])||activeHeroSlide.image_url)}
            alt={activeHeroSlide.title}
          />
          <div className="hero-slide-overlay">
            <small>PREMIUM</small>
            <h3>{activeHeroSlide.title}</h3>
            <strong>{money(activeHeroSlide.price)}</strong>
            <span><MapPin size={14}/>{activeHeroSlide.city}{activeHeroSlide.state?` - ${activeHeroSlide.state}`:''}</span>
          </div>
        </Link>

        {heroSlides.length>1 && <>
          <button type="button" className="hero-slider-arrow prev" onClick={()=>moveHeroSlide(-1)} aria-label="Anúncio anterior"><ChevronLeft/></button>
          <button type="button" className="hero-slider-arrow next" onClick={()=>moveHeroSlide(1)} aria-label="Próximo anúncio"><ChevronRight/></button>
          <div className="hero-slider-dots" aria-label="Selecionar anúncio">
            {heroSlides.map((item,index)=><button key={item.id} type="button" className={index===heroSlide?'active':''} onClick={()=>setHeroSlide(index)} aria-label={`Mostrar anúncio ${index+1}`}/>) }
          </div>
        </>}
      </div> : <div className="hero-slider-empty">
        <Sparkles/>
        <b>Seus anúncios ganham vida aqui.</b>
        <span>Anúncios Premium ativos aparecem aqui.</span>
      </div>}
    </div>
  </section>

  <section className="section category-section" id="categorias">
    <div className="section-head"><div><span className="section-kicker">EXPLORE</span><h2>Categorias</h2></div><button className="text-btn" onClick={()=>chooseCategory('')}>Ver todas <ChevronRight/></button></div>
    <div className="category-grid premium-category-grid">{categories.map(c=><button key={c.slug} className={`category-card ${cat===c.slug?'active':''}`} onClick={()=>chooseCategory(c.slug)}><span>{c.icon}</span><b>{c.name}</b></button>)}</div>
  </section>

  {partnerTop.length>0 && <section className="section partner-top-section" aria-label="Publicidade de parceiro Premium">
    {partnerTop.map(ad=><PartnerAdSpot key={ad.id} ad={ad} variant="hero"/>)}
  </section>}

  {featured.length>0 && <section className="section dark-section"><div className="section-head light"><div><span className="section-kicker">PATROCINADOS</span><h2>Anúncios em destaque</h2></div></div><div className="horizontal-cards">{featured.map(p=><ProductCard key={p.id} p={p}/>)}</div></section>}

  {plans.length>0 && <section className="section plans-highlight-section" id="planos">
    <div className="plans-highlight-head">
      <div>
        <span className="section-kicker">PLANOS DE DESTAQUE</span>
        <h2>Grátis, Plus e Premium</h2>
        <p>O plano <b>Grátis</b> é uma cortesia de <b>1 anúncio por conta durante 7 dias</b>. Depois disso, Plus e Premium oferecem mais tempo, visibilidade e benefícios comerciais.</p>
      </div>
      <Link className="primary" to="/publicar">Publicar anúncio</Link>
    </div>
    <div className="plans-highlight-grid colorful-plans-grid">
      {plans.map((plan, index)=>{
        const tier=tierClass(index, plans.length);
        return <article key={plan.code} className={`plan-teaser-card ${tier} ${index===plans.length-1?'recommended':''}`}>
          <div className="plan-top-badges">
            <span className="plan-mini-kicker">{tier==='basic'?'Grátis':tier==='plus'?'Plus':'Premium'}</span>
            {tier==='plus' && <span className="plan-chip sold">Mais vendido</span>}
            {tier==='plus' && <span className="plan-chip value">Melhor custo-benefício</span>}
            {tier==='premium' && <span className="plan-chip premium-chip">Mais vantagens</span>}
          </div>
          <h3>{plan.name}</h3>
          <div className="plan-teaser-price">{plan.free?'Grátis':money(plan.amount)}</div>
          <p>{plan.tagline||'Destaque seu anúncio por mais tempo e aumente sua chance de venda.'}</p>
          {(plan.features||[]).length>0 && <ul>
            {(plan.features||[]).map((feature)=><li key={feature}>{feature}</li>)}
          </ul>}
          {(plan.limitations||[]).length>0 && <ul className="plan-limit-list">
            {(plan.limitations||[]).map((item)=><li key={item}>{item}</li>)}
          </ul>}
          <Link className={`plan-cta ${tier==='plus' || tier==='premium'?'active':''}`} to="/escolher-plano">{plan.free?'Usar meu Grátis':'Quero este plano'}</Link>
        </article>
      })}
    </div>

    <div className="plan-comparison-wrap">
      <div className="comparison-head">
        <h3>Comparação visual dos planos</h3>
        <p>Veja rapidamente quais vantagens aumentam conforme o plano sobe.</p>
      </div>
      <div className="plan-comparison-table-wrap">
        <table className="plan-comparison-table">
          <thead>
            <tr>
              <th>Vantagens</th>
              <th className="basic">Grátis</th>
              <th className="plus">Plus</th>
              <th className="premium">Premium</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row)=><tr key={row.label}>
              <td>{row.label}</td>
              {row.values.map((value, i)=><td key={i}>{renderCell(value)}</td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </div>
    <div className="plans-highlight-note">Escolha o plano antes de publicar. O Grátis pode ser usado uma única vez por conta e dura 7 dias.</div>
  </section>}

  <section className="section infinite-feed-section" id="produtos"><div className="section-head"><div><span className="section-kicker">FEED DE ANÚNCIOS</span><h2>Produtos</h2></div><select value={sort} onChange={e=>setSort(e.target.value)}><option value="newest">Mais recentes</option><option value="price_low">Menor preço</option><option value="price_high">Maior preço</option><option value="popular">Mais vistos</option></select></div>
   {products.length ? <>
     <div className="product-grid infinite-product-grid">{products.map(p=><ProductCard key={p.id} p={p}/>)}</div>
     <div ref={feedEndRef} className="feed-loader">{loadingProducts?<><span className="feed-spinner"/> Carregando mais anúncios...</>:hasMore?'Role para ver mais anúncios':'Você viu todos os anúncios disponíveis no momento.'}</div>
   </> : loadingProducts ? <div className="feed-loader"><span className="feed-spinner"/> Carregando anúncios...</div> : <div className="empty"><div>🛍️</div><h3>Nenhum anúncio encontrado</h3><p>Altere os filtros ou publique o primeiro anúncio nesta região.</p></div>}

   {partnerEnd.length>0 && <div className="partner-end-block">
     <div className="partner-end-head"><div><span className="section-kicker">PARCEIROS DO CLASSIFICAJÁ</span><h3>Marcas que ajudam a movimentar negócios locais</h3></div><span className="partner-ad-note">Publicidade</span></div>
     <div className="partner-end-grid">{partnerEnd.map(ad=><PartnerAdSpot key={ad.id} ad={ad} variant="card"/>)}</div>
   </div>}
  </section>
 </>
}
