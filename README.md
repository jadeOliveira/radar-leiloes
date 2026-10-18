# radar-leiloes

Monitor diário de anúncios imobiliários públicos em Santa Catarina, com dashboard React/Vite, adaptadores Python independentes e publicação pelo GitHub Actions.

## Escopo do MVP

- Cidades configuradas em `config/monitor.json`: Joinville, Balneário Camboriú, Balneário Piçarras, Barra Velha e Rio do Sul.
- Adaptadores isolados para Portal Zuk, Caixa Imóveis, Mega Leilões, Superbid, Diego Leilões, Seu Imóvel BB, Freitas Leiloeiro, PGFN/Comprei, Sampaio Leilões, Machado Leiloeiro e o agregador Hasta.
- A descoberta percorre a busca estadual/paginada de cada fonte quando acessível e só depois seleciona as cidades configuradas. O limite de preço e o desconto são aplicados depois da coleta, na classificação.
- Persistência versionada em `data/properties.json`, `data/history.json`, `data/changes.json` e `data/last-run.json`.
- Dashboard com filtros por cidade, tipo, faixa de preço, desconto, datas, ocupação, riscos e categoria A/B.

Os adaptadores são independentes; o estado por fonte e por cidade fica em `data/last-run.json`. O agregador Hasta é consultado em páginas públicas separadas por cidade; seus registros ficam marcados como `nao_verificado` até a conferência do anúncio original.

Última coleta validada em 17/10/2026: Mega Leilões, Freitas, Sampaio e o agregador Hasta retornaram anúncios. Hasta encontrou 81 anúncios em cinco cidades; após deduplicação, 72 novos ou atualizados foram consolidados e o conjunto ficou com 75 imóveis. Os anúncios do agregador têm status `nao_verificado`, link para a página da fonte e não são tratados como URL oficial; fotos são limitadas às imagens específicas do anúncio. Leilão Imóvel e Núcleo Leilões bloquearam o runner com CAPTCHA. Portal Zuk, Caixa, Superbid, Diego Leilões, Seu Imóvel BB e Machado também bloquearam o runner com CAPTCHA; Comprei carregou sem expor resultados no formato reconhecido pelo adaptador. Nenhum coletor tenta contornar CAPTCHA, login ou bloqueios; uma fonte inacessível aparece com erro, sem apagar dados anteriores. Campos não confirmados permanecem nulos e o desconto só é calculado quando existe avaliação explicitamente identificada. A aplicação não substitui análise jurídica: confira anúncio original, edital, matrícula, débitos e situação do imóvel.

## Desenvolvimento local

Requisitos: Node.js 22+, Python 3.12+ e Chromium do Playwright.

```sh
npm ci
npm run dev
```

Para executar e validar os testes locais:

```sh
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
python -m monitor.run
```

## Automação e publicação

- `.github/workflows/collect.yml` roda diariamente às 08:00 com fuso `America/Sao_Paulo` e também permite execução manual. O job grava duração, estado, fontes, contagens e erros; atualiza os históricos quando há coleta válida e não apaga anúncios após falha de fonte.
- `.github/workflows/pages.yml` compila e publica no GitHub Pages após pushes, execução manual e diariamente às 08:20 em `America/Sao_Paulo`.
- O workflow tenta habilitar o GitHub Pages automaticamente. Se a política da conta impedir isso, habilite em **Settings → Pages → Build and deployment → Source: GitHub Actions** e execute o workflow novamente.

O painel está publicado em `https://jadeoliveira.github.io/radar-leiloes/`.
