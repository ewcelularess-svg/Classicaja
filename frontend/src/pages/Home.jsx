import React, {useEffect, useMemo, useRef, useState} from 'react';
import {ChevronLeft, ChevronRight, MapPin, Sparkles, Star} from 'lucide-react';
import {Link, useSearchParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import ProductCard from '../components/ProductCard';
import PartnerAdSpot from '../components/PartnerAdSpot';

const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function Home(){
 const [searchParams,setSearchParams]=useSearchParams();
 const [products,setProducts]=useState([]);
 const [categories,setCategories]=useState([]);
 const [partnerTop,setPartnerTop]=useState([]);
 const [partnerEnd,setPartnerEnd]=useState([]);
 const [q,setQ]=useState(searchParams.get('q')||'');
 const [cat,setCat]=useState(searchParams.get('category')||'');
 const [sort,setSort]=useState('newest');
 const [city,setCity]=useState(searchParams.get('city')||'');
 const [neighborhood,setNeighborhood]=useState(searchParams.get('neighborhood')||'');
 const [offset,setOffset]=useState(0);
 const [hasMore,setHasMore]=useState(true);
 const [loadingProducts,setLoadingProducts]=useState(false);
 const feedEndRef=useRef(null);
 const featuredTouchStart=useRef(null);
 const [featuredIndex,setFeaturedIndex]=useState(0);
 const [featuredPaused,setFeaturedPaused]=useState(false);
 const PAGE_SIZE=12;

 const productsUrl=(start=0)=>`/api/products?search=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}&city=${encodeURIComponent(city)}&neighborhood=${encodeURIComponent(neighborhood)}&sort=${sort}&limit=${PAGE_SIZE}&offset=${start}`;

 useEffect(()=>{
   api('/api/categories').then(setCategories).catch(()=>setCategories([]));
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

 function chooseCategory(slug){
   const next=cat===slug?'':slug;
   setCat(next);
   const p=new URLSearchParams(searchParams);
   if(next) p.set('category',next); else p.delete('category');
   setSearchParams(p);
 }

 const featured=useMemo(()=>products.filter(p=>p.featured_active).slice(0,6),[products]);
 const firstFeed=useMemo(()=>products.slice(0,8),[products]);
 const restFeed=useMemo(()=>products.slice(8),[products]);

 useEffect(()=>{
   if(!featured.length){ setFeaturedIndex(0); return; }
   setFeaturedIndex(i=>Math.min(i,featured.length-1));
 },[featured.length]);

 useEffect(()=>{
   if(featured.length<=1||featuredPaused) return;
   const timer=setInterval(()=>setFeaturedIndex(i=>(i+1)%featured.length),4500);
   return()=>clearInterval(timer);
 },[featured.length,featuredPaused]);

 const featuredPrev=()=>setFeaturedIndex(i=>(i-1+Math.max(featured.length,1))%Math.max(featured.length,1));
 const featuredNext=()=>setFeaturedIndex(i=>(i+1)%Math.max(featured.length,1));
 const featuredTouchEnd=e=>{
   const start=featuredTouchStart.current;
   featuredTouchStart.current=null;
   if(start==null) return;
   const end=e.changedTouches?.[0]?.clientX;
   if(end==null||Math.abs(end-start)<45) return;
   if(end<start) featuredNext(); else featuredPrev();
 };
 const activeFeatured=featured[featuredIndex];

 return <>
  <section className="section category-section clean-category-section" id="categorias">
    <div className="section-head compact-section-head"><div><span className="section-kicker">EXPLORE</span><h2>Categorias</h2></div><button className="text-btn" onClick={()=>chooseCategory('')}>Ver todas <ChevronRight/></button></div>
    <div className="category-grid premium-category-grid clean-category-grid">{categories.map(c=><button key={c.slug} className={`category-card ${cat===c.slug?'active':''}`} onClick={()=>chooseCategory(c.slug)}><span>{c.icon}</span><b>{c.name}</b></button>)}</div>
  </section>

  {featured.length>0 && activeFeatured && <section className="section featured-showcase-section featured-carousel-section">
    <div className="section-head compact-section-head featured-carousel-head"><div><span className="section-kicker">EM DESTAQUE</span><h2>Ofertas em destaque</h2></div><a className="text-btn" href="#produtos">Ver todas <ChevronRight/></a></div>

    <div className="featured-product-carousel" onMouseEnter={()=>setFeaturedPaused(true)} onMouseLeave={()=>setFeaturedPaused(false)} onTouchStart={e=>{featuredTouchStart.current=e.touches?.[0]?.clientX??null;setFeaturedPaused(true)}} onTouchEnd={e=>{featuredTouchEnd(e);setFeaturedPaused(false)}}>
      <Link key={activeFeatured.id} className="featured-carousel-slide" to={`/produto/${activeFeatured.id}`} aria-label={`Ver anúncio ${activeFeatured.title}`}>
        <div className="featured-carousel-image">
          {((activeFeatured.images&&activeFeatured.images[0])||activeFeatured.image_url)
            ? <img src={imageUrl((activeFeatured.images&&activeFeatured.images[0])||activeFeatured.image_url)} alt={activeFeatured.title}/>
            : <div className="featured-carousel-placeholder">📦</div>}
        </div>
        <div className="featured-carousel-copy">
          <div className="featured-carousel-label"><Star size={15} fill="currentColor"/> Oferta em destaque</div>
          <h3>{activeFeatured.title}</h3>
          <strong>{money(activeFeatured.price)}</strong>
          <span className="featured-carousel-location"><MapPin size={15}/>{[activeFeatured.neighborhood,activeFeatured.city,activeFeatured.state].filter(Boolean).join(' • ')}</span>
          <span className="featured-carousel-cta">Ver anúncio <ChevronRight size={16}/></span>
        </div>
      </Link>

      {featured.length>1&&<>
        <button type="button" className="featured-carousel-arrow prev" onClick={e=>{e.preventDefault();featuredPrev()}} aria-label="Oferta anterior"><ChevronLeft/></button>
        <button type="button" className="featured-carousel-arrow next" onClick={e=>{e.preventDefault();featuredNext()}} aria-label="Próxima oferta"><ChevronRight/></button>
        <div className="featured-carousel-dots" aria-label="Navegação das ofertas">{featured.map((p,i)=><button key={p.id} type="button" className={i===featuredIndex?'active':''} onClick={()=>setFeaturedIndex(i)} aria-label={`Ir para oferta ${i+1}`}/>)}</div>
      </>}
    </div>
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
