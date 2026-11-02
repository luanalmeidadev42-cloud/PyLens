# Explicação do código do PyLens

Este guia acompanha o código existente e explica como as partes se conectam. Os caminhos são relativos à raiz do projeto.

## Visão geral

O PyLens recebe um comando, inicia o script monitorado como um processo separado, coleta medições enquanto ele roda e grava o resultado no SQLite.

```text
usuário
  └─ pylens.interface:main           interpreta os argumentos
       └─ core.executor:run_script   executa e coordena a medição
            ├─ monitoring.monitor    coleta CPU e memória
            └─ database.repository   grava execução, amostras e eventos
```

Um **processo** é uma instância de um programa em execução. O processo do PyLens pode observar e encerrar o processo do script sem misturar os dois fluxos de execução. Isso não é uma sandbox: o script continua tendo as permissões do usuário.

## Experimente primeiro

Instale o projeto em modo de desenvolvimento e rode o exemplo:

```bash
python -m pip install -e .
pylens run examples/sample_workload.py -- --seconds 2
pylens history
```

O primeiro `--` separa as opções do PyLens das opções do script monitorado. Assim, `--seconds 2` chega ao exemplo, não ao PyLens.

## O caminho de uma execução

1. `src/pylens/__main__.py` permite iniciar o programa com `python -m pylens` e encaminha o controle para a CLI.
2. `src/pylens/interface/cli.py` interpreta `run`, `history` ou `delete`. Para `run`, transforma os valores recebidos em um objeto `Settings` e chama `run_script`.
3. `src/pylens/core/executor.py` valida os caminhos, registra a execução como `RUNNING` e inicia o script com `subprocess.Popen`.
4. Enquanto o processo está vivo, o executor pede uma amostra ao `ProcessMonitor`, grava essa amostra e verifica timeout, memória e CPU.
5. Quando termina, `core.classifier` avalia o resultado, o tempo, os picos de CPU e memória e a qualidade das medições. O executor grava a classificação e seus motivos no histórico e devolve um `RunResult` para a CLI exibir.

O **código de saída** é um número que o programa devolve ao sistema operacional. Em geral, `0` significa sucesso; outro valor indica falha ou uma condição especial.

## O que é medido

`src/pylens/monitoring/monitor.py` usa a biblioteca `psutil` para observar o processo principal e seus processos filhos:

- **CPU (%):** tempo de processador observado entre amostras. Pode passar de 100% quando mais de um núcleo é usado.
- **RSS:** memória física atualmente ocupada pelo processo. O PyLens soma os valores do processo e dos filhos encontrados.
- **VMS:** espaço de memória virtual reservado pelo processo e seus filhos.
- **Threads:** fluxos de execução ativos somados na árvore de processos.
- **Processos:** quantidade de processos encontrados na árvore naquele instante.

Uma **amostra** é uma medição pontual. O modo normal mede aproximadamente a cada segundo; `detailed` e `deep`, a cada 100 milissegundos. Como a medição não é contínua, um pico entre duas amostras pode não aparecer. Se o PyLens não consegue observar toda a árvore, registra os valores como desconhecidos em vez de apresentar uma soma incompleta como se fosse exata.

Os limites de memória e CPU são comparados com as amostras da árvore de processos. O padrão de CPU é 100%, equivalente a um núcleo lógico totalmente ocupado. Ao atingir um limite ou o timeout, o executor tenta encerrar o processo e seus filhos. Como a checagem usa amostras, o encerramento pode ocorrer depois que o uso real já ultrapassou o valor configurado.

## Modos de execução

- `normal`: monitora recursos sem instrumentar as funções Python.
- `detailed`: além das amostras, executa o script com `cProfile` e mostra as funções com maior tempo acumulado.
- `deep`: coleta o mesmo perfil por função e também mede o tempo de parede acumulado em cada linha do script monitorado.

**Perfil** é um resumo de onde o programa gastou tempo. O perfil por linha usa tracing de Python e mede tempo de parede inclusivo: o tempo gasto dentro de uma função chamada por uma linha também conta nessa linha. Ele ajuda a escolher o que investigar, mas não explica sozinho a causa da lentidão. A instrumentação, principalmente em `deep`, pode alterar o tempo observado.

## Módulos do projeto

### Interface de linha de comando

- `src/pylens/interface/cli.py`: define argumentos e subcomandos, chama o executor, imprime resultados e converte o resultado em código de saída do PyLens. Também implementa a consulta e exclusão de execuções.
- `src/pylens/interface/interactive.py`: oferece um menu guiado que coleta opções por perguntas e encaminha as ações aos mesmos handlers da CLI.
- `src/pylens/interface/__main__.py`: permite abrir o menu guiado com `python -m pylens.interface`.
- `src/pylens/__main__.py`: ponto de entrada para `python -m pylens`.
- `src/pylens/__init__.py`: marca o diretório como pacote Python.

### Configuração e execução

- `src/pylens/config/settings.py`: guarda os valores padrão, valida modo/timeout/memória e calcula o caminho do banco padrão.
- `src/pylens/core/executor.py`: contém `run_script`, que coordena o ciclo inteiro; `RunResult` representa os dados devolvidos à CLI. Funções auxiliares montam o comando de perfil, leem a saída limitada aos últimos 1 MiB e encerram a árvore de processos.
- `src/pylens/core/classifier.py`: classifica a execução como `NORMAL`, `WARNING`, `CRITICAL` ou `UNDETERMINED` e explica os fatores que levaram ao resultado.
- `src/pylens/core/models.py`: reservado para modelos de domínio; não é usado pelo fluxo atual.

### Monitoramento e relatórios

- `src/pylens/monitoring/monitor.py`: define `ProcessSample` (o formato de uma amostra) e `ProcessMonitor` (a coleta usando `psutil`).
- `src/pylens/monitoring/profiler.py`: coordena `cProfile` nos modos `detailed` e `deep`, e tracing por linha do script alvo no modo `deep`.
- `src/pylens/reports/formatter.py`: espaço para formatação de relatórios; não é chamado pela CLI atual.

### Banco de dados

- `src/pylens/database/connection.py`: cria o diretório do banco, abre a conexão SQLite, liga as chaves estrangeiras e aplica o esquema.
- `src/pylens/database/database.sql`: define as tabelas `executions`, `samples` e `logs`, suas validações, relações e índices.
- `src/pylens/database/repository.py`: agrupa as operações SQL para criar/finalizar execuções, inserir amostras e eventos, consultar histórico e logs e excluir execuções concluídas. `ON DELETE CASCADE` faz o SQLite apagar amostras e logs associados quando uma execução é excluída.
- `src/pylens/database/migrations/`: espaço reservado para migrações do esquema; ainda não há migrações implementadas.

### Exemplo e interface antiga

- `examples/sample_workload.py`: gera uma carga curta de CPU para experimentar a medição; limita a duração para no máximo 15 segundos.
- `src/pylens/interface/`: contém a CLI de comandos (`pylens`, `python -m pylens`) e o menu guiado (`pylens-menu`, `python -m pylens.interface`). As duas interfaces encaminham as ações para a mesma CLI.

### Testes

- `tests/test_executor.py`, `tests/test_models.py`, `tests/test_database.py` e `tests/test_classifier.py`: verificam partes do executor, modelos, persistência e classificador. A existência de testes não significa que eles foram executados nesta alteração.

## Histórico local

O esquema do SQLite organiza os dados em três grupos:

1. `executions`: uma linha por script executado, com caminho, modo, status, tempos e limites usados.
2. `samples`: medições de recursos associadas à execução.
3. `logs`: eventos como início, limite atingido, falha ou perfil coletado.

O padrão é `~/.pylens/history.sqlite3`. `--database` permite escolher outro caminho. Os argumentos do script também ficam registrados nesse banco local; não passe segredos pela linha de comando se não quiser que sejam armazenados.

## Limites a lembrar

- O monitoramento por amostras pode perder picos curtos.
- Um subprocesso separado não restringe as permissões do script.
- `cProfile` mede funções Python, mas não detalha o trabalho interno de bibliotecas nativas.
- A saída mostrada mantém apenas o último 1 MiB de cada fluxo (`stdout` e `stderr`).
- No estado atual, `deep` não mede tempo por linha.
