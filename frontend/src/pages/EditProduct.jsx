import React,{useEffect,useMemo,useState} from 'react';
import {ArrowLeft, GripVertical, Save, Star, Trash2, UploadCloud} from 'lucide-react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';

export default function EditProduct(){
 const {id}=useParams();
 const nav=useNavigate();
 const [cats,setCats]=useState([]);
 const [form,setForm]=useState(null);
 const [gallery,setGallery]=useState([]);
 const [newFiles,setNewFiles]=useState([]);
 const [newPreviews,setNewPreviews]=useState([]);
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const [galleryBusy,setGalleryBusy]=useState(false);
 const [dragIndex,setDragIndex]=useState(null);

 useEffect(()=>{
  Promise.all([api('/api/categories'),api(`/api/products/${id}`)])
   .then(([categories,p])=>{
    setCats(categories);
    setGallery((p.images&&p.images.length?p.images:(p.image_url?[p.image_url]:[]))||[]);
    setForm({
     title:p.title||'', description:p.description||'', price:p.price??'', original_price:p.original_price??'',
     category_slug:p.category_slug||'', city:p.city||'', state:p.state||'PR',
     neighborhood:p.neighborhood||'', condition:p.condition||'Usado', status:p.status||'active'
    });
   }).catch(e=>setErr(e.message));
 },[id]);

 const remainingSlots = useMemo(()=>Math.max(0,8-gallery.length-newFiles.length),[gallery.length,newFiles.length]);
 const change=e=>setForm({...form,[e.target.name]:e.target.value});

 const submit=async e=>{
  e.preventDefault(); setErr(''); setBusy(true);
  try{
   const payload={...form,price:Number(form.price),state:String(form.state||'').toUpperCase()};
   if(payload.original_price===''||payload.original_price===null) payload.original_price=null;
   else payload.original_price=Number(payload.original_price);

   await api(`/api/products/${id}`,{method:'PUT',body:JSON.stringify(payload)});

   if(newFiles.length){
    const fd=new FormData();
    newFiles.forEach(file=>fd.append('images',file));
    await api(`/api/products/${id}/gallery/add`,{method:'POST',body:fd});
   }

   nav(`/produto/${id}`);
  }catch(e){setErr(e.message)}finally{setBusy(false)}
 };

 const onFiles=e=>{
  const available=Math.max(0,8-gallery.length);
  const files=Array.from(e.target.files||[]).slice(0,available);
  newPreviews.forEach(src=>URL.revokeObjectURL(src));
  setNewFiles(files);
  setNewPreviews(files.map(f=>URL.createObjectURL(f)));
 };

 const removePendingImage=index=>{
  URL.revokeObjectURL(newPreviews[index]);
  setNewFiles(files=>files.filter((_,i)=>i!==index));
  setNewPreviews(previews=>previews.filter((_,i)=>i!==index));
 };

 const removeImage=async(img)=>{
  if(!confirm('Deseja remover esta foto da galeria?')) return;
  setGalleryBusy(true); setErr('');
  try{
    const res=await api(`/api/products/${id}/gallery/image`,{method:'DELETE',body:JSON.stringify({image_url:img})});
    setGallery(res.images||[]);
  }catch(e){setErr(e.message)}finally{setGalleryBusy(false)}
 };

 const setAsPrimary=async(img)=>{
  const next=[img,...gallery.filter(x=>x!==img)];
  setGallery(next);
  setGalleryBusy(true); setErr('');
  try{
    const res=await api(`/api/products/${id}/gallery/order`,{method:'PUT',body:JSON.stringify({images:next})});
    setGallery(res.images||next);
  }catch(e){setErr(e.message)}finally{setGalleryBusy(false)}
 };

 const moveGallery=async(from,to)=>{
  if(from===to || from===null || to===null || to<0 || to>=gallery.length) return;
  const next=[...gallery];
  const [item]=next.splice(from,1);
  next.splice(to,0,item);
  setGallery(next);
  setGalleryBusy(true); setErr('');
  try{
    const res=await api(`/api/products/${id}/gallery/order`,{method:'PUT',body:JSON.stringify({images:next})});
    setGallery(res.images||next);
  }catch(e){setErr(e.message)}finally{setGalleryBusy(false);setDragIndex(null)}
 };

 if(err&&!form) return <div className="page narrow"><div className="empty"><h3>{err}</h3><Link className="primary" to="/meus-anuncios">Voltar aos anúncios</Link></div></div>;
 if(!form) return <div className="loading">Carregando anúncio...</div>;

 return <div className="page publish-page edit-page">
  <Link className="back" to="/meus-anuncios"><ArrowLeft/> Voltar para meus anúncios</Link>
  <div className="form-card"><div><span className="section-kicker">EDITAR CLASSIFICADO</span><h1>Editar anúncio</h1><p>Organize a galeria, selecione novas fotos e salve tudo de uma só vez.</p></div>

   <div className="gallery-manager">
    <div className="gallery-manager-head">
      <div>
        <h3>Galeria do anúncio</h3>
        <p>Arraste as fotos para reordenar. A primeira foto é a principal.</p>
      </div>
      <span className="gallery-counter">{gallery.length+newFiles.length}/8 fotos</span>
    </div>

    <div className="gallery-manager-grid">
      {gallery.map((img,index)=><div
        key={img}
        className={`gallery-manager-card ${index===0?'primary':''}`}
        draggable
        onDragStart={()=>setDragIndex(index)}
        onDragOver={(e)=>e.preventDefault()}
        onDrop={()=>moveGallery(dragIndex,index)}
      >
        <div className="drag-chip"><GripVertical size={14}/> Arraste</div>
        {index===0 && <div className="primary-chip"><Star size={12}/> Principal</div>}
        <img src={imageUrl(img)} alt={`Foto ${index+1}`}/>
        <div className="gallery-manager-actions">
          {index!==0 && <button type="button" onClick={()=>setAsPrimary(img)} disabled={galleryBusy}><Star size={15}/> Definir principal</button>}
          <button type="button" className="danger-lite" onClick={()=>removeImage(img)} disabled={galleryBusy || gallery.length<=1}><Trash2 size={15}/> Remover</button>
        </div>
      </div>)}
    </div>

    <div className="gallery-add-box">
      <div className="gallery-add-copy">
        <b>Adicionar mais fotos</b>
        <span>{newFiles.length ? `${newFiles.length} nova(s) foto(s) pronta(s). Clique em “Salvar alterações” para enviar.` : `Você ainda pode incluir ${Math.max(0,8-gallery.length)} foto(s) nesta galeria.`}</span>
      </div>
      <label className="gallery-add-input">
        <UploadCloud/>
        <span>{newFiles.length?'Trocar seleção':'Selecionar imagens'}</span>
        <input type="file" accept="image/*" multiple onChange={onFiles} disabled={gallery.length>=8}/>
      </label>
    </div>

    {newPreviews.length>0 && <div className="gallery-new-preview">{newPreviews.map((src,i)=><div className="pending-image-card" key={src}><img src={src} alt={`Nova foto ${i+1}`}/><button type="button" onClick={()=>removePendingImage(i)} aria-label="Remover foto selecionada"><Trash2 size={14}/></button></div>)}</div>}
   </div>

   <form onSubmit={submit} className="publish-form">
    <label>Título do anúncio<input name="title" value={form.title} onChange={change} required/></label>
    <label>Descrição<textarea name="description" value={form.description} onChange={change} rows="5" required/></label>
    <div className="two-cols"><label>Preço (R$)<input name="price" value={form.price} onChange={change} type="number" min="0" step="0.01" required/></label><label>Preço anterior / promoção (opcional)<input name="original_price" value={form.original_price} onChange={change} type="number" min="0" step="0.01" placeholder="Ex.: 2500.00"/></label></div>
    <div className="two-cols"><label>Condição<select name="condition" value={form.condition} onChange={change}><option>Novo</option><option>Seminovo</option><option>Usado</option></select></label><label>Status do anúncio<select name="status" value={form.status} onChange={change}><option value="active">Ativo</option><option value="paused">Pausado</option><option value="sold">Vendido</option></select></label></div>
    <label>Categoria<select name="category_slug" value={form.category_slug} onChange={change} required><option value="">Selecione</option>{cats.map(c=><option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
    <div className="three-cols"><label>Cidade<input name="city" value={form.city} onChange={change} required/></label><label>Bairro<input name="neighborhood" value={form.neighborhood} onChange={change}/></label><label>UF<input name="state" value={form.state} onChange={change} maxLength="2" required/></label></div>
    {err&&<div className="form-error">{err}</div>}
    <button className="primary wide" disabled={busy||galleryBusy}><Save/>{busy?'Salvando anúncio e fotos...':'Salvar alterações'}</button>
   </form>
  </div>
 </div>
}
