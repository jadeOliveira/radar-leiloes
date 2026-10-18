# radar-leiloes

Painel inicial para acompanhar oportunidades imobiliárias em leilões. O projeto combina uma página React/Vite, um coletor Python com Playwright e publicação por GitHub Actions.

## Escopo do MVP

- Dashboard em português com busca, filtros por cidade e tipo e indicador prioritário para imóveis de até R$ 800 mil com desconto de pelo menos 30%.
- Coleta diária de anúncios públicos do Portal Zuk para Rio do Sul/SC, com gravação em `public/data/auctions.json`.
- Publicação do painel no GitHub Pages.

A coleta é inicial e limitada a uma fonte e uma cidade. A extração depende da estrutura pública do Portal Zuk e pode precisar de manutenção caso a página mude. O coletor não faz análise jurídica, não confirma ocupação ou situação registral e não deve ser tratado como cobertura completa de leilões. Confirme os dados no anúncio e edital oficiais.

## Desenvolvimento local

Requisitos: Node.js 22+, Python 3.12+ e Chromium do Playwright.

```sh
npm ci
npm run dev
```

Para atualizar os dados manualmente:

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/collect_zuk.py
```

## Automação e publicação

- `.github/workflows/collect.yml` roda diariamente às 08:00 no horário de Brasília (11:00 UTC) e também permite execução manual. Alterações no JSON são registradas em um commit automático.
- `.github/workflows/pages.yml` compila e publica no GitHub Pages em pushes para `main`, execução manual e diariamente às 08:20 de Brasília. O agendamento separado assegura a republicação dos dados mesmo quando o commit do coletor, feito pelo `GITHUB_TOKEN`, não inicia outro workflow.
- O workflow tenta habilitar o GitHub Pages automaticamente. Se a política da conta impedir isso, habilite em **Settings → Pages → Build and deployment → Source: GitHub Actions** e execute o workflow novamente.

O endereço padrão do painel será `https://jadeOliveira.github.io/radar-leiloes/` após o primeiro deploy bem-sucedido.
