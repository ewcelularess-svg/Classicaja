import React,{useEffect,useState} from 'react';
import {CheckCircle2, Headphones, Lightbulb, Flag, Send, ShieldCheck} from 'lucide-react';
import {useSearchParams} from 'react-router-dom';
import {api} from '../lib/api';
import {useAuth} from '../main';

const OPTIONS={
  reclamacao:{api:'complaint',label:'Reclamação',title:'Registrar uma reclamação',description:'Conte o que aconteceu. Sua mensagem ficará registrada para análise.',Icon:Flag,tone:'complaint'},
  suporte:{api:'support',label:'Suporte',title:'Como podemos ajudar?',description:'Descreva sua dúvida ou dificuldade para que possamos entender o caso.',Icon:Headphones,tone:'support'},
  sugestao:{api:'suggestion',label:'Sugestão',title:'Compartilhe sua ideia',description:'Sua sugestão pode ajudar a tornar o ClassificaJá ainda melhor.',Icon:Lightbulb,tone:'suggestion'},
};

export default function Support(){
  const {user}=useAuth();
  const [params,setParams]=useSearchParams();
  const requested=params.get('tipo');
  const initial=OPTIONS[requested]?requested:'suporte';
  const [type,setType]=useState(initial);
  const [form,setForm]=useState({name:user?.name||'',email:user?.email||'',subject:'',message:''});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [protocol,setProtocol]=useState('');
  const current=OPTIONS[type];
  const CurrentIcon=current.Icon;

  useEffect(()=>{
    const next=params.get('tipo');
    if(OPTIONS[next]&&next!==type)setType(next);
  },[params]);
  useEffect(()=>{
    if(user)setForm(v=>({...v,name:user.name||v.name,email:user.email||v.email}));
  },[user]);

  const selectType=(key)=>{
    setType(key);setError('');setProtocol('');
    setParams({tipo:key},{replace:true});
  };

  const submit=async(e)=>{
    e.preventDefault();setBusy(true);setError('');setProtocol('');
    try{
      const result=await api('/api/support-requests',{method:'POST',body:JSON.stringify({category:current.api,...form})});
      setProtocol(result.protocol||'REGISTRADO');
      setForm(v=>({...v,subject:'',message:''}));
    }catch(err){setError(err.message||'Não foi possível enviar sua mensagem.');}
    finally{setBusy(false)}
  };

  const fieldsDisabled=Boolean(user);
  return <div className="support-page">
    <section className="support-hero">
      <div className="support-hero-badge"><ShieldCheck/> Central de atendimento</div>
      <h1>Fale com o ClassificaJá</h1>
      <p>Escolha o assunto e envie sua mensagem. Tudo fica organizado em um protocolo para acompanhamento interno.</p>
    </section>

    <section className="support-shell">
      <div className="support-type-grid">
        {Object.entries(OPTIONS).map(([key,item])=>{const Icon=item.Icon;return <button type="button" key={key} className={`support-type-card ${item.tone} ${type===key?'active':''}`} onClick={()=>selectType(key)}>
          <span><Icon/></span><b>{item.label}</b><small>{key==='reclamacao'?'Problemas e ocorrências':key==='suporte'?'Dúvidas e ajuda':'Ideias e melhorias'}</small>
        </button>})}
      </div>

      <div className={`support-form-card ${current.tone}`}>
        <div className="support-form-heading">
          <span className="support-form-icon"><CurrentIcon/></span>
          <div><span>{current.label.toUpperCase()}</span><h2>{current.title}</h2><p>{current.description}</p></div>
        </div>

        {protocol?<div className="support-success"><CheckCircle2/><div><b>Mensagem enviada com sucesso</b><span>Protocolo: <strong>{protocol}</strong></span><small>Nossa equipe poderá usar o e-mail informado para dar continuidade ao atendimento.</small></div></div>:null}
        {error?<div className="support-error">{error}</div>:null}

        <form className="support-form" onSubmit={submit}>
          <div className="support-form-grid">
            <label>Seu nome<input value={form.name} disabled={fieldsDisabled} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Nome completo" required/></label>
            <label>Seu e-mail<input type="email" value={form.email} disabled={fieldsDisabled} onChange={e=>setForm({...form,email:e.target.value})} placeholder="voce@email.com" required/></label>
          </div>
          {user&&<div className="support-account-note"><ShieldCheck/> Envio vinculado à sua conta ClassificaJá.</div>}
          <label>Assunto<input value={form.subject} onChange={e=>setForm({...form,subject:e.target.value})} maxLength="180" placeholder={type==='reclamacao'?'Ex.: problema com um anúncio':type==='suporte'?'Ex.: dúvida sobre meu plano':'Ex.: ideia para melhorar o site'} required/></label>
          <label>Mensagem<textarea rows="7" value={form.message} onChange={e=>setForm({...form,message:e.target.value})} maxLength="4000" placeholder="Descreva com detalhes para facilitar o atendimento." required/></label>
          <div className="support-form-footer"><small>{form.message.length}/4000 caracteres</small><button className="primary" disabled={busy}><Send/>{busy?'Enviando...':'Enviar mensagem'}</button></div>
        </form>
      </div>
    </section>
  </div>;
}
