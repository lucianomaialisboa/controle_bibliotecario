# Biblioteca: controle de empréstimos

Aplicação web simples para registrar empréstimos de livros da biblioteca escolar.
É feita em Python (Flask) e guarda tudo num único arquivo SQLite (`biblioteca.db`).

## O que ela faz

- **Login de usuários** (bibliotecários, professores, etc.). No primeiro acesso o sistema pede para criar o **administrador**.
- **Usuários** (só para administradores): criar usuários, redefinir senha e desativar/reativar. Cada usuário pode trocar a própria senha.
- **Empréstimos** (tela inicial): escolha o aluno e o livro, ou use **"＋ Cadastrar novo aluno"** / **"＋ Cadastrar novo livro"** para cadastrar na hora. O prazo padrão é de 7 dias.
- Lista dos empréstimos em aberto, com os **atrasados em vermelho** e o botão **Devolver**.
- **Quem fez o quê**: o sistema grava qual usuário cadastrou cada aluno e cada livro, qual usuário fez cada empréstimo e qual recebeu cada devolução (com data e hora).
- **Histórico** com busca por aluno, turma, livro ou usuário.
- **Alunos** e **Livros**: cadastro e edição. Livros têm quantidade de exemplares, e o sistema não deixa emprestar quando não há exemplar disponível.

## 1. Criar o container no Proxmox

1. No Proxmox, baixe o template **Debian 12** (local › CT Templates › Templates › `debian-12-standard`).
2. Clique em **Create CT**:
   - Hostname: `biblioteca`
   - Senha do root: a sua escolha
   - Template: `debian-12-standard`
   - Disco: 4 GB já sobra
   - CPU: 1 núcleo · Memória: 512 MB
   - Rede: `vmbr0`, IPv4 **DHCP** (ou um IP fixo, recomendado, por ex. `192.168.0.50/24` com o gateway da sua rede)
3. Inicie o container e abra o **Console**. Entre como `root`.

## 2. Copiar os arquivos para o container

A pasta do projeto tem estes arquivos:

```
app.py  instalar.sh  biblioteca.service  LEIAME.md  templates/  static/
```

Escolha uma forma de copiar:

- **Pelo host Proxmox** (copie a pasta para o host e depois para o container, onde `101` é o número do CT):
  ```sh
  tar czf biblioteca.tar.gz biblioteca
  pct push 101 biblioteca.tar.gz /root/biblioteca.tar.gz
  pct exec 101 -- tar xzf /root/biblioteca.tar.gz -C /root
  ```
- **Por SCP** do seu computador: `scp -r biblioteca root@IP_DO_CONTAINER:/root/`
  (no Debian do LXC talvez seja preciso liberar login do root por SSH ou usar o primeiro método).

## 3. Instalar

No console do container:

```sh
cd /root/biblioteca
sh instalar.sh
```

O script instala Python, Flask e Waitress pelo `apt`, copia o programa para `/opt/biblioteca`,
cria o serviço `biblioteca` e já deixa ele iniciando junto com o container.
No final ele mostra o endereço, por exemplo `http://192.168.0.50:8080`.

## 4. Primeiro acesso

Abra o endereço no navegador. Na primeira vez aparece a tela **Primeiro acesso**: crie o administrador
(seu nome, login e senha). Depois vá em **Usuários** para criar os logins das outras pessoas.
Marque "administrador" só para quem também puder gerenciar usuários.

## Uso diário

| Ação | Como fazer |
|---|---|
| Emprestar | Tela **Empréstimos** › escolha aluno e livro › **Registrar empréstimo** |
| Aluno ou livro novo | No próprio campo, escolha **＋ Cadastrar novo…** e preencha |
| Devolver | Botão **Devolver** na lista de empréstimos em aberto |
| Ver quem emprestou | Colunas **Por** / **Emprestado por** e **Recebido por** no Histórico |
| Corrigir um cadastro | Menus **Alunos** ou **Livros** › **editar** |
| Esqueceu a senha | Um administrador redefine em **Usuários** |

## Manutenção

```sh
systemctl status biblioteca      # ver se está rodando
systemctl restart biblioteca     # reiniciar
journalctl -u biblioteca -f      # ver o log
```

**Backup**: todos os dados ficam em `/opt/biblioteca/biblioteca.db`. Copie esse arquivo regularmente,
ou faça backup do container inteiro pelo Proxmox (Datacenter › Backup).

**Atualizar o programa**: copie os novos arquivos para `/root/biblioteca` e rode `sh instalar.sh` de novo.
O banco de dados é mantido.

**Administrador perdeu a senha**: no console do container, gere uma senha nova assim
(troque `luciano` e `novasenha`):

```sh
cd /opt/biblioteca
python3 -c "import sqlite3; from werkzeug.security import generate_password_hash as h; c=sqlite3.connect('biblioteca.db'); c.execute('UPDATE usuarios SET senha_hash=?, ativo=1 WHERE login=?', (h('novasenha'), 'luciano')); c.commit()"
```

**Configurações** (opcional, em `/etc/systemd/system/biblioteca.service`, depois `systemctl daemon-reload && systemctl restart biblioteca`):

- `BIBLIOTECA_PORT`: porta (padrão `8080`)
- `BIBLIOTECA_PRAZO_DIAS`: prazo padrão do empréstimo em dias (padrão `7`)

## Observação de segurança

O sistema foi pensado para a **rede interna da escola**. Não exponha a porta 8080 na internet.
Se precisar de acesso de fora, use uma VPN ou um proxy com HTTPS na frente.
