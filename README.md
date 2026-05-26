# Copa Mundo Novo - Fantasy League

Simulador e album de jogadores inspirado em Copa do Mundo. O projeto tem um
backend em FastAPI, banco SQLite e uma interface web em HTML, CSS e JavaScript.

## Como funciona

- O usuario cria conta, faz login e recebe um token JWT.
- Cada conta tem gemas para abrir pacotes de selecoes e pacotes de jogadores.
- As cartas de jogadores ficam no album, podem ter quantidades repetidas e
  podem ser usadas na escalacao personalizada.
- A simulacao usa a forca da escalacao, bonus por quantidade de cartas e
  momento das selecoes para gerar placar e narrativa.
- O administrador pode gerenciar usuarios, gemas, cartas e resultados globais.
- As imagens dos jogadores ficam em `assets/players`. Nesta versao, o seed do
  banco so mantem jogadores que possuem imagem local associada.

## Como baixar

### Pelo Git

```bash
git clone https://github.com/PabloPenna41/Fantasy-League.git
cd Fantasy-League
```

### Pelo GitHub

1. Abra `https://github.com/PabloPenna41/Fantasy-League`.
2. Clique em `Code`.
3. Clique em `Download ZIP`.
4. Extraia o ZIP e abra a pasta do projeto.

## Como rodar

Crie e ative um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependencias:

```bash
pip install -r requirements.txt
```

Inicie o backend:

```bash
python -m uvicorn main:app --reload
```

A API fica em:

```text
http://localhost:8000
```

A documentacao interativa fica em:

```text
http://localhost:8000/docs
```

Para abrir a interface, use o arquivo `index.html`. Uma forma simples e servir
a pasta do projeto em outro terminal:

```bash
python3 -m http.server 5500
```

Depois acesse:

```text
http://localhost:5500/index.html
```

## Banco de dados

O projeto usa SQLite por padrao. O arquivo `worldcup.db` e criado
automaticamente na primeira execucao e fica fora do Git por causa do
`.gitignore`.

Na inicializacao, o backend:

- cria as tabelas necessarias;
- aplica migracoes simples para bancos antigos;
- popula ou atualiza jogadores e selecoes;
- remove jogadores sem imagem local associada;
- cria o usuario administrador padrao.

## Testes

Para rodar os testes existentes:

```bash
python test_backend.py
```

## Estrutura principal

- `main.py`: rotas FastAPI, seed, migracoes e regras principais.
- `models.py`: modelos SQLAlchemy.
- `schemas.py`: modelos Pydantic usados pela API.
- `database.py`: configuracao do SQLite.
- `jogadores.py`: catalogo editavel dos jogadores.
- `teams_data.py`: dados das selecoes.
- `simulation.py`: logica de simulacao das partidas.
- `index.html`: interface web.
- `assets/`: icones e imagens dos jogadores.

## Adicionar ou corrigir jogadores

1. Coloque a imagem PNG em `assets/players`.
2. Edite o jogador em `jogadores.py`.
3. Se o nome exibido for diferente do nome antigo no banco, use
   `original_name`.
4. Se o arquivo da imagem tiver um nome levemente diferente, adicione um alias
   em `PLAYER_PHOTO_ALIASES`.
5. Reinicie o backend para o seed atualizar o banco.
