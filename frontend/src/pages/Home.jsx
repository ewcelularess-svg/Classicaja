import React, {useEffect, useMemo, useState} from 'react';
import {Check, ChevronRight, MapPin, Search, ShieldCheck, Sparkles, Tag, Users, X} from 'lucide-react';
import {Link, useSearchParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import ProductCard from '../components/ProductCard';

const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const rows = [
  {label:'Publicação normal no marketplace', values:[true,true,true]},
  {label:'Selo de anúncio em destaque', values:[false,true,true]},
  {label:'Prioridade nas buscas', values:['Sem prioridade','Maior','Máxima']},
  {label:'Tempo em evidência', values:['Sem destaque','15 dias','30 dias']},
  {label:'Melhor posição no catálogo', values:[false,true,true]},
  {label:'Mais visualizações no catálogo', values:[false,false,true]},
  {label:'Maior exposição entre anúncios', values:[false,false,true]},
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
 const [q,setQ]=useState(searchParams.get('q')||'');
 const [cat,setCat]=useState(searchParams.get('category')||'');
 const [sort,setSort]=useState('newest');
 const [city,setCity]=useState(searchParams.get('city')||'');
 const [neighborhood,setNeighborhood]=useState(searchParams.get('neighborhood')||'');

 const load=()=>api(`/api/products?search=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}&city=${encodeURIComponent(city)}&neighborhood=${encodeURIComponent(neighborhood)}&sort=${sort}`).then(setProducts).catch(()=>setProducts([]));

 useEffect(()=>{
   api('/api/categories').then(setCategories);
   api('/api/public/stats').then(setStats).catch(()=>{});
   api('/api/plans').then(setPlans).catch(()=>setPlans([]));
 },[]);

 useEffect(()=>{
   const nextQ=searchParams.get('q')||'';
   const nextCity=searchParams.get('city')||'';
   const nextNeighborhood=searchParams.get('neighborhood')||'';
   const nextCategory=searchParams.get('category')||'';
   setQ(nextQ); setCity(nextCity); setNeighborhood(nextNeighborhood); setCat(nextCategory);
 },[searchParams]);

 useEffect(()=>{const t=setTimeout(load,250); return ()=>clearTimeout(t)},[q,cat,sort,city,neighborhood]);

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
 const preview=products[0];

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

    <div className="market-hero-visual" aria-hidden="true">
      <div className="hero-orb hero-orb-one"/><div className="hero-orb hero-orb-two"/>
      <div className="phone-mockup">
        <div className="phone-speaker"/>
        <div className="phone-screen">
          <img className="phone-logo" src="/logo-classificaja.png" alt=""/>
          <div className="phone-search"><Search/><span>Buscar produtos...</span></div>
          <div className="phone-categories"><span>🚗<small>Carros</small></span><span>📱<small>Celulares</small></span><span>🏠<small>Imóveis</small></span></div>
          <div className="phone-product">
            <div className="phone-product-img">{preview?.image_url?<img src={imageUrl(preview.image_url)} alt=""/>:<span>🛍️</span>}</div>
            <div><small>{preview?.category_name||'Anúncio local'}</small><b>{preview?.title||'Seu produto aqui'}</b><strong>{preview?.price?money(preview.price):'R$ 0,00'}</strong></div>
          </div>
        </div>
      </div>
      <div className="hero-promo-copy">Tudo<br/>o que você<br/>procura,<br/><em>mais perto<br/>de você.</em></div>
    </div>
  </section>

  <section className="section category-section" id="categorias">
    <div className="section-head"><div><span className="section-kicker">EXPLORE</span><h2>Categorias</h2></div><button className="text-btn" onClick={()=>chooseCategory('')}>Ver todas <ChevronRight/></button></div>
    <div className="category-grid premium-category-grid">{categories.map(c=><button key={c.slug} className={`category-card ${cat===c.slug?'active':''}`} onClick={()=>chooseCategory(c.slug)}><span>{c.icon}</span><b>{c.name}</b></button>)}</div>
  </section>

  {featured.length>0 && <section className="section dark-section"><div className="section-head light"><div><span className="section-kicker">PATROCINADOS</span><h2>Anúncios em destaque</h2></div></div><div className="horizontal-cards">{featured.map(p=><ProductCard key={p.id} p={p}/>)}</div></section>}

  {plans.length>0 && <section className="section plans-highlight-section" id="planos">
    <div className="plans-highlight-head">
      <div>
        <span className="section-kicker">PLANOS DE DESTAQUE</span>
        <h2>Grátis, Plus e Premium</h2>
        <p>O plano <b>Grátis</b> mantém o anúncio publicado de forma normal, sem recursos de destaque. O <b>Plus</b> adiciona visibilidade e o <b>Premium</b> entrega o máximo de exposição.</p>
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
          <Link className={`plan-cta ${tier==='plus' || tier==='premium'?'active':''}`} to="/publicar">{plan.free?'Publicar grátis':'Quero este plano'}</Link>
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
    <div className="plans-highlight-note">Você ativa o plano logo após publicar o anúncio, sem complicação.</div>
  </section>}

  <section className="section" id="produtos"><div className="section-head"><div><span className="section-kicker">CLASSIFICADOS</span><h2>Produtos</h2></div><select value={sort} onChange={e=>setSort(e.target.value)}><option value="newest">Mais recentes</option><option value="price_low">Menor preço</option><option value="price_high">Maior preço</option><option value="popular">Mais vistos</option></select></div>
   {products.length ? <div className="product-grid">{products.map(p=><ProductCard key={p.id} p={p}/>)}</div> : <div className="empty"><div>🛍️</div><h3>Nenhum anúncio encontrado</h3><p>Altere os filtros ou publique o primeiro anúncio nesta região.</p></div>}
  </section>
 </>
}
