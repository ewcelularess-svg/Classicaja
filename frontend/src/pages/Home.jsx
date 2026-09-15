import React, {useEffect, useMemo, useRef, useState} from 'react';
import {ChevronLeft, ChevronRight, MapPin, Search, ShieldCheck, Sparkles, Tag, Users} from 'lucide-react';
import {Link, useSearchParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import ProductCard from '../components/ProductCard';
import PartnerAdSpot from '../components/PartnerAdSpot';

const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function Home(){
 const [searchParams,setSearchParams]=useSearchParams();
 const [products,setProducts]=useState([]);
 const [categories,setCategories]=useState([]);
 const [stats,setStats]=useState({products:0,sellers:0,cities:0});
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
   api('/api/categories').then(setCategories).catch(()=>setCategories([]));
   api('/api/public/stats').then(setStats).catch(()=>{});
   api('/api/partner-ads?slot=home_top&limit=1').then(setPartnerTop).catch(()=>setPartnerTop([]));
   api('/api/partner-ads?slot=feed_end&limit=1').then(setPartnerEnd).catch(()=>setPartnerEnd([]));
 },[]);

 useEffect(()=>{
   setQ(searchParams.get('q')||'');
   setCity(searchParams.get('city')||'');
   setNeighborhood(searchParams.get('neighborhood')||'');
   setCat(searchParams.get('category')||'');
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
   },220);
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

 const featured=useMemo(()=>products.filter(p=>p.featured_active).slice(0,6),[products]);
 const heroSlides=useMemo(()=>products.filter(p=>p.featured_active && Number(p.boost_level||0)>=3 && ((p.images&&p.images[0])||p.image_url)).slice(0,6),[products]);
 const activeHeroSlide=heroSlides[heroSlide]||heroSlides[0]||null;
 const firstFeed=useMemo(()=>products.slice(0,8),[products]);
 const restFeed=useMemo(()=>products.slice(8),[products]);

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
  <section className="market-hero clean-market-hero">
    <div className="market-hero-copy clean-hero-copy">
      <span className="eyebrow">COMPRE E VENDA PERTO DE VOCÊ</span>
      <h1>Seu marketplace local, simples e direto.</h1>
      <p>Encontre boas oportunidades na sua região e anuncie sem complicação.</p>

      <form className="market-search clean-market-search" onSubmit={submitSearch}>
        <div className="market-search-main"><Search/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="O que você está procurando?"/></div>
        <button type="submit">Buscar</button>
      </form>
      <div className="market-location-row clean-location-row">
        <label><MapPin/><input value={city} onChange={e=>setCity(e.target.value)} placeholder="Cidade"/></label>
        <label><input value={neighborhood} onChange={e=>setNeighborhood(e.target.value)} placeholder="Bairro"/></label>
      </div>

      <div className="market-benefits clean-benefits">
        <div><ShieldCheck/><span><b>Verificados</b><small>Mais segurança</small></span></div>
        <div><Tag/><span><b>Venda direta</b><small>Sem intermediários</small></span></div>
        <div><Sparkles/><span><b>Destaques</b><small>Mais visibilidade</small></span></div>
        <div><Users/><span><b>Marketplace local</b><small>Na sua região</small></span></div>
      </div>

      <div className="market-stats clean-stats" aria-label="Estatísticas do marketplace">
        <span><b>{stats.products}</b> anúncios</span>
        <span><b>{stats.sellers}</b> usuários</span>
        <span><b>{stats.cities}</b> cidades</span>
      </div>
    </div>

    <div className="market-hero-visual hero-slider-visual clean-hero-slider">
      <div className="hero-slider-heading">
        <span>EM ALTA AGORA</span>
        <b>Veja o que acabou de chegar</b>
      </div>

      {activeHeroSlide ? <div className="hero-live-slider">
        <Link className="hero-live-slide" to={`/produto/${activeHeroSlide.id}`}>
          <img src={imageUrl((activeHeroSlide.images&&activeHeroSlide.images[0])||activeHeroSlide.image_url)} alt={activeHeroSlide.title}/>
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
        <b>Boas oportunidades perto de você.</b>
        <span>Anúncios Premium aparecem neste espaço.</span>
      </div>}
    </div>
  </section>

  <section className="section category-section clean-category-section" id="categorias">
    <div className="section-head compact-section-head"><div><span className="section-kicker">EXPLORE</span><h2>Categorias</h2></div><button className="text-btn" onClick={()=>chooseCategory('')}>Ver todas <ChevronRight/></button></div>
    <div className="category-grid premium-category-grid clean-category-grid">{categories.map(c=><button key={c.slug} className={`category-card ${cat===c.slug?'active':''}`} onClick={()=>chooseCategory(c.slug)}><span>{c.icon}</span><b>{c.name}</b></button>)}</div>
  </section>

  {featured.length>0 && <section className="section featured-showcase-section">
    <div className="section-head compact-section-head"><div><span className="section-kicker">EM DESTAQUE</span><h2>Ofertas em destaque</h2></div><a className="text-btn" href="#produtos">Ver todas <ChevronRight/></a></div>
    <div className="horizontal-cards clean-horizontal-cards">{featured.map(p=><ProductCard key={p.id} p={p}/>)}</div>
  </section>}

  <section className="section infinite-feed-section clean-feed-section" id="produtos">
    <div className="section-head compact-section-head feed-title-row">
      <div><span className="section-kicker">PARA VOCÊ</span><h2>Produtos perto de você</h2></div>
      <select value={sort} onChange={e=>setSort(e.target.value)}><option value="newest">Mais recentes</option><option value="price_low">Menor preço</option><option value="price_high">Maior preço</option><option value="popular">Mais vistos</option></select>
    </div>

    {products.length ? <>
      <div className="product-grid infinite-product-grid clean-product-grid">{firstFeed.map(p=><ProductCard key={p.id} p={p}/>)}</div>

      {partnerTop.length>0 && <div className="feed-inline-partner" aria-label="Publicidade de parceiro Premium">
        {partnerTop.map(ad=><PartnerAdSpot key={ad.id} ad={ad} variant="strip"/>)}
      </div>}

      <div className="home-plan-strip">
        <div><Sparkles/><span><b>Venda mais com Plus e Premium</b><small>Mais visibilidade, destaque e benefícios comerciais.</small></span></div>
        <Link to="/escolher-plano">Ver planos</Link>
      </div>

      {restFeed.length>0 && <div className="product-grid infinite-product-grid clean-product-grid secondary-feed-grid">{restFeed.map(p=><ProductCard key={p.id} p={p}/>)}</div>}

      <div ref={feedEndRef} className="feed-loader">{loadingProducts?<><span className="feed-spinner"/> Carregando mais anúncios...</>:hasMore?'Role para ver mais anúncios':'Você viu todos os anúncios disponíveis no momento.'}</div>
    </> : loadingProducts ? <div className="feed-loader"><span className="feed-spinner"/> Carregando anúncios...</div> : <div className="empty"><div>🛍️</div><h3>Nenhum anúncio encontrado</h3><p>Altere os filtros ou publique o primeiro anúncio nesta região.</p></div>}

    {partnerEnd.length>0 && <div className="partner-end-block clean-partner-end">
      <div className="partner-end-head"><div><span className="section-kicker">PARCEIRO</span><h3>Oferta de parceiro</h3></div><span className="partner-ad-note">Publicidade</span></div>
      <div className="partner-end-grid">{partnerEnd.map(ad=><PartnerAdSpot key={ad.id} ad={ad} variant="strip"/>)}</div>
    </div>}
  </section>
 </>
}
