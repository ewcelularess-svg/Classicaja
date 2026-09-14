import React,{useEffect,useState} from 'react';
import {ArrowLeft, Camera, Save} from 'lucide-react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';

export default function EditProduct(){
 const {id}=useParams();
 const nav=useNavigate();
 const [cats,setCats]=useState([]);
 const [form,setForm]=useState(null);
 const [currentImage,setCurrentImage]=useState('');
 const [image,setImage]=useState(null);
 const [preview,setPreview]=useState(null);
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);

 useEffect(()=>{
  Promise.all([api('/api/categories'),api(`/api/products/${id}`)])
   .then(([categories,p])=>{
    setCats(categories);
    setCurrentImage(p.image_url||'');
    setForm({
     title:p.title||'', description:p.description||'', price:p.price??'',
     category_slug:p.category_slug||'', city:p.city||'', state:p.state||'PR',
     neighborhood:p.neighborhood||'', condition:p.condition||'Usado', status:p.status||'active'
    });
   }).catch(e=>setErr(e.message));
 },[id]);

 const change=e=>setForm({...form,[e.target.name]:e.target.value});
 const submit=async e=>{
  e.preventDefault(); setErr(''); setBusy(true);
  try{
   const payload={...form,price:Number(form.price),state:String(form.state||'').toUpperCase()};
   await api(`/api/products/${id}`,{method:'PUT',body:JSON.stringify(payload)});
   if(image){
    const fd=new FormData(); fd.append('image',image);
    await api(`/api/products/${id}/image`,{method:'POST',body:fd});
   }
   nav(`/produto/${id}`);
  }catch(e){setErr(e.message)}finally{setBusy(false)}
 };

 if(err&&!form) return <div className="page narrow"><div className="empty"><h3>{err}</h3><Link className="primary" to="/meus-anuncios">Voltar aos anúncios</Link></div></div>;
 if(!form) return <div className="loading">Carregando anúncio...</div>;
 const shownPreview=preview || (currentImage?imageUrl(currentImage):null);

 return <div className="page publish-page edit-page">
  <Link className="back" to="/meus-anuncios"><ArrowLeft/> Voltar para meus anúncios</Link>
  <div className="form-card"><div><span className="section-kicker">EDITAR CLASSIFICADO</span><h1>Editar anúncio</h1><p>Atualize as informações do seu produto. As alterações entram no ar após salvar.</p></div>
   <form onSubmit={submit} className="publish-form">
    <label className="upload-box">{shownPreview?<img src={shownPreview}/>:<><Camera/><b>Adicionar foto principal</b><span>JPG, PNG ou WEBP • até 7 MB</span></>}<span className="edit-photo-hint">Clique para {currentImage?'trocar':'adicionar'} a foto</span><input type="file" accept="image/*" onChange={e=>{const f=e.target.files[0];setImage(f||null);setPreview(f?URL.createObjectURL(f):null)}}/></label>
    <label>Título do anúncio<input name="title" value={form.title} onChange={change} required/></label>
    <label>Descrição<textarea name="description" value={form.description} onChange={change} rows="5" required/></label>
    <div className="two-cols"><label>Preço (R$)<input name="price" value={form.price} onChange={change} type="number" min="0" step="0.01" required/></label><label>Condição<select name="condition" value={form.condition} onChange={change}><option>Novo</option><option>Seminovo</option><option>Usado</option></select></label></div>
    <label>Categoria<select name="category_slug" value={form.category_slug} onChange={change} required><option value="">Selecione</option>{cats.map(c=><option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
    <div className="three-cols"><label>Cidade<input name="city" value={form.city} onChange={change} required/></label><label>Bairro<input name="neighborhood" value={form.neighborhood} onChange={change}/></label><label>UF<input name="state" value={form.state} onChange={change} maxLength="2" required/></label></div>
    <label>Status do anúncio<select name="status" value={form.status} onChange={change}><option value="active">Ativo</option><option value="paused">Pausado</option><option value="sold">Vendido</option></select></label>
    {err&&<div className="form-error">{err}</div>}
    <button className="primary wide" disabled={busy}><Save/>{busy?'Salvando...':'Salvar alterações'}</button>
   </form>
  </div>
 </div>
}
