import React,{useEffect,useState} from 'react';
import {Camera, CheckCircle2} from 'lucide-react';
import {api} from '../lib/api';
import {useNavigate} from 'react-router-dom';
export default function Publish(){
 const [cats,setCats]=useState([]); const [form,setForm]=useState({title:'',description:'',price:'',category_slug:'',city:'',state:'PR',neighborhood:'',condition:'Usado'}); const [image,setImage]=useState(null); const [preview,setPreview]=useState(null); const [err,setErr]=useState(''); const [busy,setBusy]=useState(false); const nav=useNavigate();
 useEffect(()=>{api('/api/categories').then(setCats)},[]);
 const change=e=>setForm({...form,[e.target.name]:e.target.value});
 const submit=async e=>{e.preventDefault(); setErr(''); setBusy(true); try{const fd=new FormData();Object.entries(form).forEach(([k,v])=>fd.append(k,v));if(image)fd.append('image',image);const r=await api('/api/products',{method:'POST',body:fd});nav(`/produto/${r.id}`)}catch(e){setErr(e.message)}finally{setBusy(false)}};
 return <div className="page publish-page"><div className="form-card"><div><span className="section-kicker">NOVO CLASSIFICADO</span><h1>Publique seu produto</h1><p>Seu anúncio entra no marketplace e poderá receber mensagens de compradores.</p></div><form onSubmit={submit} className="publish-form">
  <label className="upload-box">{preview?<img src={preview}/>:<><Camera/><b>Adicionar foto principal</b><span>JPG, PNG ou WEBP • até 7 MB</span></>}<input type="file" accept="image/*" onChange={e=>{const f=e.target.files[0];setImage(f);setPreview(f?URL.createObjectURL(f):null)}}/></label>
  <label>Título do anúncio<input name="title" value={form.title} onChange={change} placeholder="Ex.: iPhone 15 128 GB" required/></label><label>Descrição<textarea name="description" value={form.description} onChange={change} rows="5" placeholder="Estado do produto, detalhes, acessórios..." required/></label>
  <div className="two-cols"><label>Preço (R$)<input name="price" value={form.price} onChange={change} type="number" min="0" step="0.01" required/></label><label>Condição<select name="condition" value={form.condition} onChange={change}><option>Novo</option><option>Seminovo</option><option>Usado</option></select></label></div>
  <label>Categoria<select name="category_slug" value={form.category_slug} onChange={change} required><option value="">Selecione</option>{cats.map(c=><option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
  <div className="three-cols"><label>Cidade<input name="city" value={form.city} onChange={change} required/></label><label>Bairro<input name="neighborhood" value={form.neighborhood} onChange={change}/></label><label>UF<input name="state" value={form.state} onChange={change} maxLength="2" required/></label></div>{err&&<div className="form-error">{err}</div>}<button className="primary wide" disabled={busy}><CheckCircle2/>{busy?'Publicando...':'Publicar anúncio'}</button>
 </form></div></div>
}
