import React,{useEffect,useRef,useState} from 'react';
import {Camera, CheckCircle2, ImagePlus} from 'lucide-react';
import {api} from '../lib/api';
import {useNavigate} from 'react-router-dom';

export default function Publish(){
 const [cats,setCats]=useState([]);
 const [form,setForm]=useState({title:'',description:'',price:'',original_price:'',payment_mode:'cash',category_slug:'',city:'',state:'PR',neighborhood:'',condition:'Usado'});
 const [images,setImages]=useState([]);
 const [previews,setPreviews]=useState([]);
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const galleryInputRef=useRef(null);
 const cameraInputRef=useRef(null);
 const nav=useNavigate();
 useEffect(()=>{api('/api/categories').then(setCats)},[]);
 const change=e=>setForm({...form,[e.target.name]:e.target.value});
 const addFiles=(fileList)=>{
  const incoming=Array.from(fileList||[]);
  if(!incoming.length) return;
  setImages(current=>{
   const room=Math.max(0,8-current.length);
   const chosen=incoming.slice(0,room);
   if(!chosen.length) return current;
   setPreviews(currentPreviews=>[...currentPreviews,...chosen.map(f=>URL.createObjectURL(f))]);
   return [...current,...chosen];
  });
 };
 const onFiles=e=>{addFiles(e.target.files);e.target.value='';};
 const removeSelectedImage=index=>{
  setPreviews(current=>{
   const target=current[index];
   if(target) URL.revokeObjectURL(target);
   return current.filter((_,i)=>i!==index);
  });
  setImages(current=>current.filter((_,i)=>i!==index));
 };
 const submit=async e=>{
  e.preventDefault(); setErr(''); setBusy(true);
  try{
   const fd=new FormData();
   Object.entries(form).forEach(([k,v])=>{ if(v!=='' && v!==null && v!==undefined) fd.append(k,v); });
   images.forEach(file=>fd.append('images',file));
   const r=await api('/api/products',{method:'POST',body:fd});
   nav(`/produto/${r.id}`)
  }catch(e){setErr(e.message)}finally{setBusy(false)}
 };
 return <div className="page publish-page"><div className="form-card"><div><span className="section-kicker">NOVO CLASSIFICADO</span><h1>Publique seu produto</h1><p>Adicione várias fotos, destaque promoção e venda com mais chances no marketplace.</p></div><form onSubmit={submit} className="publish-form">
  <div className="upload-box multi-upload-box photo-source-box">
    {previews.length?
      <div className="multi-preview-grid selectable-preview-grid">{previews.map((src,i)=><div className="selected-photo-card" key={src}><img src={src} alt={`Prévia ${i+1}`}/><button type="button" onClick={()=>removeSelectedImage(i)} aria-label={`Remover foto ${i+1}`}>×</button></div>)}</div>
      :<><ImagePlus/><b>Adicionar fotos do anúncio</b><span>Selecione até 8 fotos • JPG, PNG ou WEBP • até 7 MB cada</span></>}
    <div className="photo-source-actions">
      <button type="button" className="photo-source-btn gallery-photo-btn" onClick={()=>galleryInputRef.current?.click()} disabled={images.length>=8}><ImagePlus/><span>Galeria</span></button>
      <button type="button" className="photo-source-btn camera-photo-btn" onClick={()=>cameraInputRef.current?.click()} disabled={images.length>=8}><Camera/><span>Câmera</span></button>
    </div>
    <small className="photo-source-help">No celular, toque em <b>Galeria</b> para escolher fotos existentes.</small>
    <input ref={galleryInputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={onFiles}/>
    <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" onChange={onFiles}/>
  </div>
  <label>Título do anúncio<input name="title" value={form.title} onChange={change} placeholder="Ex.: iPhone 15 128 GB" required/></label><label>Descrição<textarea name="description" value={form.description} onChange={change} rows="5" placeholder="Estado do produto, detalhes, acessórios..." required/></label>
  <div className="two-cols"><label>Preço (R$)<input name="price" value={form.price} onChange={change} type="number" min="0" step="0.01" required/></label><label>Preço anterior / promoção (opcional)<input name="original_price" value={form.original_price} onChange={change} type="number" min="0" step="0.01" placeholder="Ex.: 2500.00"/></label></div>
  <div className="payment-choice-box">
    <div><b>Forma de venda</b><span>Escolha como pretende negociar a venda com o comprador. O ClassificaJá não participa nem intermedeia o parcelamento entre comprador e vendedor.</span></div>
    <div className="payment-choice-options">
      <label className={form.payment_mode==='cash'?'selected':''}><input type="radio" name="payment_mode" value="cash" checked={form.payment_mode==='cash'} onChange={change}/><span><b>À vista</b><small>Pagamento único</small></span></label>
      <label className={form.payment_mode==='installments'?'selected':''}><input type="radio" name="payment_mode" value="installments" checked={form.payment_mode==='installments'} onChange={change}/><span><b>Parcelado</b><small>Negociação direta com o comprador</small></span></label>
    </div>
  </div>
  <div className="two-cols"><label>Condição<select name="condition" value={form.condition} onChange={change}><option>Novo</option><option>Seminovo</option><option>Usado</option></select></label><div className="promo-hint-box"><Camera/><div><b>Dica:</b><span>Se o preço anterior for maior que o preço atual, o anúncio receberá o selo <b>Promoção</b>.</span></div></div></div>
  <label>Categoria<select name="category_slug" value={form.category_slug} onChange={change} required><option value="">Selecione</option>{cats.map(c=><option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
  <div className="three-cols"><label>Cidade<input name="city" value={form.city} onChange={change} required/></label><label>Bairro<input name="neighborhood" value={form.neighborhood} onChange={change}/></label><label>UF<input name="state" value={form.state} onChange={change} maxLength="2" required/></label></div>{err&&<div className="form-error">{err}</div>}<button className="primary wide" disabled={busy}><CheckCircle2/>{busy?'Publicando...':'Publicar anúncio'}</button>
 </form></div></div>
}
