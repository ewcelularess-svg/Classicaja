import React from 'react';
import {ChevronRight, Handshake} from 'lucide-react';
import {imageUrl} from '../lib/api';

const tierLabel=tier=>tier==='premium'?'Premium':tier==='plus'?'Plus':'Grátis';

export default function PartnerAdSpot({ad,variant='strip',className=''}){
  if(!ad) return null;
  const tier=ad.plan_tier||'free';
  const body=<>
    {ad.image_url&&<div className="partner-spot-image"><img src={imageUrl(ad.image_url)} alt={ad.company_name}/></div>}
    <div className="partner-spot-copy">
      <span className={`partner-spot-kicker tier-${tier}`}><Handshake/> PARCEIRO {tierLabel(tier).toUpperCase()}</span>
      <b>{ad.company_name}</b>
      <strong>{ad.title}</strong>
      {ad.subtitle&&<p>{ad.subtitle}</p>}
      <span className="partner-spot-link">Conhecer parceiro <ChevronRight/></span>
    </div>
  </>;
  const cls=`partner-spot partner-spot-${variant} tier-${tier} ${className}`.trim();
  return ad.target_url
    ? <a className={cls} href={ad.target_url} target="_blank" rel="noreferrer sponsored">{body}</a>
    : <div className={cls}>{body}</div>;
}
