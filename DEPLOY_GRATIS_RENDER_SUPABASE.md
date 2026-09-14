# Publicar o ClassificaJá grátis — Supabase + Render

Esta versão já foi preparada para PostgreSQL e Storage persistentes. Em produção, não usamos SQLite nem a pasta local de uploads.

## 1. Criar o projeto no Supabase

1. Entre no Supabase e crie um projeto gratuito.
2. Defina uma senha forte para o banco e guarde-a.
3. Aguarde o projeto ficar pronto.

## 2. Copiar a conexão PostgreSQL correta

No painel do Supabase:

1. Clique em **Connect**.
2. Escolha **Session pooler**.
3. Use a conexão da porta **5432**.
4. Copie a URL completa e substitua o campo da senha pela senha do banco.

Ela será cadastrada no Render como:

`DATABASE_URL`

**Importante:** para Render, use o **Session pooler IPv4**. Não use a conexão direta `db.<project>.supabase.co`, pois a conexão direta do plano gratuito é normalmente IPv6.

## 3. Copiar URL e Secret Key do Supabase

No Supabase, abra as configurações de API/Connect e copie:

- Project URL → `SUPABASE_URL`
- Secret key, iniciada por `sb_secret_...` → `SUPABASE_SECRET_KEY`

A Secret Key é exclusivamente do backend. Nunca coloque essa chave em React, JavaScript público, screenshots ou GitHub público.

## 4. Storage de fotos

O backend tenta criar automaticamente um bucket público chamado:

`product-images`

Se a criação automática não funcionar:

1. Abra **Storage** no Supabase.
2. Clique em **New Bucket**.
3. Nome: `product-images`.
4. Marque o bucket como **Public**.
5. Salve.

As fotos passam a usar URLs permanentes do Supabase Storage.

## 5. Colocar o projeto no GitHub

Crie um repositório e envie **o conteúdo desta pasta**. O arquivo `render.yaml` precisa ficar na raiz do repositório.

Não envie arquivos `.env` com segredos. A `.gitignore` já está configurada para ignorá-los.

## 6. Criar o serviço no Render

No Render:

1. Entre em **New > Blueprint**.
2. Conecte o repositório GitHub do ClassificaJá.
3. O Render encontrará `render.yaml`.
4. Durante a criação, informe os segredos solicitados.

Preencha:

- `DATABASE_URL`: conexão **Session pooler** do Supabase.
- `SUPABASE_URL`: URL do projeto Supabase.
- `SUPABASE_SECRET_KEY`: Secret Key `sb_secret_...`.
- `ADMIN_EMAIL`: seu e-mail de administrador.
- `ADMIN_PASSWORD`: uma senha forte para o painel admin.

O restante já está configurado.

## 7. O que o Render fará sozinho

O Render usa o `Dockerfile` incluído no projeto. O build:

1. cria um estágio Node para instalar o React;
2. executa `npm run build`;
3. cria a imagem Python do backend;
4. instala `requirements.txt`;
5. copia `frontend/dist` para a imagem final;
6. inicia o FastAPI com Uvicorn.

O Docker evita depender de Node estar instalado no runtime Python do Render.

## 8. Validar depois do deploy

Abra:

`https://SEU-SITE.onrender.com/api/health`

O esperado é algo parecido com:

```json
{
  "ok": true,
  "service": "ClassificaJá",
  "version": "2.2.0",
  "database": "postgresql",
  "storage": "supabase"
}
```

Depois abra a URL principal do Render. O React será servido pelo próprio backend e funcionará tanto no celular quanto no notebook.

## 9. Primeiro acesso administrativo

Use o e-mail e a senha que você colocou em `ADMIN_EMAIL` e `ADMIN_PASSWORD` no Render.

A versão de produção não cria a conta de demonstração `admin@classificaja.com` automaticamente.

## 10. Limitações do plano gratuito

O Web Service gratuito do Render pode entrar em suspensão quando fica sem acessos. Na primeira visita depois desse período, a API pode levar alguns segundos para responder. Banco e imagens continuam persistentes no Supabase.

## 11. Pagamentos

PIX e cartão ainda estão em **modo demonstrativo**. Não use o botão de confirmação simulada para cobrança real. A próxima etapa é conectar Mercado Pago ou outro gateway e validar pagamentos por webhook.
