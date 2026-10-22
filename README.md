# radar-leiloes

Monitor diário de anúncios imobiliários públicos em Santa Catarina, com dashboard React/Vite, adaptadores Python independentes e publicação pelo GitHub Actions.

## Escopo do MVP

- Cidades configuradas em `config/monitor.json`: Joinville, Balneário Camboriú, Balneário Piçarras, Barra Velha, Penha, Navegantes e Rio do Sul.
- Adaptadores isolados para Portal Zuk (busca estadual), Caixa Imóveis, Mega Leilões, Superbid, Diego Leilões, Duarte Leilões Oficiais, Zampieri Leiloeiro, Seu Imóvel BB, Freitas Leiloeiro, PGFN/Comprei, Sampaio Leilões, Machado Leiloeiro e o agregador Hasta.
- A descoberta percorre a busca estadual/paginada de cada fonte quando acessível e só depois seleciona as cidades configuradas. O limite de preço e o desconto são aplicados depois da coleta, na classificação.
- Persistência versionada em `data/properties.json`, `data/history.json`, `data/changes.json` e `data/last-run.json`.
- Dashboard com filtros por cidade, tipo, faixa de preço, desconto, datas, ocupação, riscos e categoria A/B; cartões mostram valores da 1ª e 2ª praça e o lance mínimo vigente quando disponíveis.
- O feed publica somente casas, apartamentos, terrenos e galpões. Um anúncio classificado genericamente como “lote” só entra se o próprio anúncio trouxer indicação explícita de terreno. Portais mistos são filtrados após a descoberta; registros sem tipo confirmado ou de bens móveis são removidos da lista atual e preservados como eventos no histórico.

Os adaptadores são independentes; o estado por fonte e por cidade fica em `data/last-run.json`. O agregador Hasta é consultado em páginas públicas separadas por cidade; seus registros ficam marcados como `nao_verificado` até a conferência do anúncio original. No painel, a visão padrão mostra somente imóveis descobertos nos últimos sete dias, com selo “NOVO”; “Somente ativos” mostra toda a lista ativa. Assim, a consulta diária começa pelas novidades, sem repetir a revisão de todos os anúncios. Ativos são agrupados por cidade e ordenados pela data do leilão; a data aparece em cada cartão quando disponível. Datas futuras sem sinal de abertura aparecem em `scheduled_unverified` na opção “Ativos e próximos”; datas passadas sem confirmação de resultado aparecem como `ended_unverified`. Cancelamento, suspensão e venda só são registrados quando há texto explícito da fonte. A opção “Todos os anúncios” inclui também histórico e situação desconhecida.

`data/properties.json` só é regravado quando há um imóvel novo ou uma mudança relevante confirmada. Se nenhuma fonte encontrar novidades, o arquivo e seu horário de atualização permanecem intactos; `data/last-run.json` registra a execução mais recente e o painel informa que os dados exibidos são da última atualização de conteúdo. Se todas as fontes falharem, os anúncios anteriores também são preservados e o painel sinaliza a coleta indisponível.

Na coleta de 19/10/2026, a base preservada continha 207 imóveis. Mega Leilões, Freitas, Sampaio e o agregador Hasta retornaram anúncios; Hasta percorreu as páginas públicas por cidade. Duarte e Zampieri foram adicionados para a próxima execução, com base nos anúncios públicos encontrados em seus sites oficiais. Os anúncios de agregadores têm status `nao_verificado`, link para a página da fonte e não são tratados como URLs oficiais. Fotos são lidas do card e da galeria do anúncio individual. A Hasta abre cada detalhe para coletar apenas a galeria daquele imóvel, sem aproveitar fotos de anúncios semelhantes nem alterar preços com o texto da página. O painel tenta as imagens seguintes quando a primeira falha e só indica ausência quando todas falham ou a fonte não publica foto. Portal Zuk, Caixa, Superbid, Diego Leilões, Seu Imóvel BB e Machado bloquearam o runner com CAPTCHA; Comprei carregou sem expor resultados no formato reconhecido pelo adaptador. Nenhum coletor tenta contornar CAPTCHA, login ou bloqueios; uma fonte inacessível aparece com erro, sem apagar dados anteriores. Campos não confirmados permanecem nulos e o desconto só é calculado quando existe avaliação explicitamente identificada. A aplicação não substitui análise jurídica: confira anúncio original, edital, matrícula, débitos e situação do imóvel.

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

- A automação local do Codex deve executar a coleta diária no checkout do repositório, às 08:00 em `America/Sao_Paulo`. Ela consulta todas as fontes e páginas públicas acessíveis antes de classificar os anúncios, preserva a base e o histórico, registra o relatório em `data/last-run.json` e só cria commit/push para `main` quando há alterações.
- `.github/workflows/collect.yml` mantém apenas `workflow_dispatch` para uma coleta manual. Não há `push` nem `schedule`, evitando uma segunda coleta automática no GitHub Actions.
- `.github/workflows/pages.yml` compila e publica após cada push para `main`, além de permitir publicação manual. O GitHub Actions publica os dados versionados; não executa uma coleta automática.
- O filtro **Novos** exibe somente imóveis com `newly_discovered_at` no dia corrente em `America/Sao_Paulo`. No dia seguinte, eles continuam em **Todos** e deixam de aparecer em **Novos**. Os cards novos exibem endereço, bairro, título, origem e links de validação quando conhecidos.
- O workflow tenta habilitar o GitHub Pages automaticamente. Se a política da conta impedir isso, habilite em **Settings → Pages → Build and deployment → Source: GitHub Actions** e execute o workflow novamente.

Para configurar a automação local, abra `/Users/jade/dev/workspace/radar-leiloes` como projeto local no Codex e crie uma automação diária às 08:00 (`America/Sao_Paulo`) com estas instruções: pesquise todos os anúncios nas fontes e cidades de `config/monitor.json`, percorrendo todas as páginas acessíveis antes de aplicar filtros; respeite bloqueios, CAPTCHA e autenticação; não invente dados e mantenha desconhecidos como `null`; preserve identidade e histórico; só marque como novos os imóveis encontrados pela primeira vez hoje e registre mudanças em imóveis conhecidos; atualize os arquivos de dados existentes, registre estado e erros por fonte e continue as demais fontes quando uma falhar; valide JSON, duplicidades e fotos sem apagar dados válidos; revise o diff e faça commit/push para `main` somente se houver alterações, com mensagem `data: atualização diária dos leilões`.

O painel está publicado em `https://jadeoliveira.github.io/radar-leiloes/`.

### Fotos dos anúncios

Em 20/10/2026, as galerias dos 21 anúncios de Balneário Camboriú foram conferidas individualmente e suas URLs adicionadas à base (antes, somente cinco tinham imagem). As fotos permanecem hospedadas nas fontes públicas; não são substituídas por imagens de outros imóveis. O coletor abre os detalhes da Hasta nas próximas execuções para renovar essas URLs. Se a fonte remover ou bloquear todas as fotos, o cartão informa a ausência.

A revisão foi ampliada para todos os 131 anúncios da base em 20/10/2026: todos receberam URLs de fotos. Foram conferidas as 128 páginas da Hasta; três galerias ausentes no agregador foram recuperadas nos leiloeiros originais, com identidade do lote/bem conferida. A origem das fotos recuperadas fica em `image_source_url` e o resumo em `data/image-report.json`. As próximas coletas já abrem os detalhes da Hasta em todas as cidades configuradas, sem restrição a Balneário Camboriú; registros históricos preservam as fotos recuperadas.

### Regra obrigatória do agendamento: fotos

Toda geração agendada tenta recuperar fotos ausentes abrindo anúncios individuais da base, inclusive registros históricos e todas as cidades. Usa somente fotos vinculadas ao próprio imóvel, preserva as fotos existentes e não contorna bloqueios, login ou CAPTCHA. A etapa `monitor.ensure_images` registra recuperações e pendências em `data/image-report.json`. Antes de publicar, `monitor.photo_policy` rejeita URLs de imagem inválidas; quando a fonte não oferece uma foto verificável, a publicação continua e o card usa o placeholder “Foto não disponível na fonte”. Não inventar imagens nem usar fotos de outros imóveis. A verificação de URLs não garante disponibilidade futura do servidor de origem; o painel tenta as fotos alternativas em caso de falha.
