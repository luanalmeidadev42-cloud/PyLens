# Referência de sintaxes do PyLens

Este documento explica as formas de uso e as estruturas principais presentes no projeto. Os comandos abaixo pressupõem que o PyLens foi instalado com `python -m pip install -e .` ou que está sendo executado no ambiente do projeto.

## Sintaxe geral da CLI

```text
pylens <comando> [opções]
```

`pylens` inicia o programa, `<comando>` escolhe a operação e `[opções]` configura essa operação. Os colchetes indicam itens opcionais; eles não devem ser digitados literalmente. Os comandos disponíveis são `run`, `history`, `logs` e `delete`.

## Executar um script: `run`

```text
pylens run <script> [opções do PyLens] [-- <argumentos do script>]
```

- `run` inicia e monitora um programa Python em outro processo.
- `<script>` é o caminho para o arquivo Python que será executado.
- As opções antes de `--` pertencem ao PyLens.
- O separador `--` encerra as opções do PyLens. Tudo depois dele é entregue ao script, sem interpretação pelo PyLens.
- Se o script não precisa de argumentos, omita `--` e a parte final.

Exemplos:

```bash
pylens run examples/sample_workload.py
pylens run examples/sample_workload.py -- --seconds 3
pylens run tarefa.py --mode detailed --timeout 60 --memory-limit-mib 512 --cpu-limit-percent 100 -- --entrada dados.csv
```

### Opções de `run`

| Sintaxe | Significado | Padrão / valores aceitos |
| --- | --- | --- |
| `--mode <modo>` | Seleciona o nível de instrumentação. | `normal`; também `detailed` e `deep` |
| `--timeout <segundos>` | Tempo máximo antes de encerrar a execução. | `120`; inteiro maior que zero |
| `--memory-limit-mib <MiB>` | Limite de RSS somado da árvore de processos, em mebibytes. | `2048`; inteiro maior que zero |
| `--cpu-limit-percent <percentual>` | Limite de CPU agregado da árvore de processos. 100% equivale ao uso total de um núcleo lógico; a soma pode passar de 100% em vários núcleos. | `100`; número maior que zero |
| `--workdir <diretório>` | Diretório de trabalho do script. | Diretório atual |
| `--database <caminho>` | Arquivo SQLite para o histórico local. | `~/.pylens/history.sqlite3` |

Os limites de memória e CPU são verificados pelas amostras e podem detectar um pico com atraso. Eles não restringem o processo como uma sandbox do sistema operacional.

### Modos

| Modo | Coleta |
| --- | --- |
| `normal` | Amostras de recursos aproximadamente a cada 1 segundo, sem perfil de funções. |
| `detailed` | Amostras aproximadamente a cada 100 ms e resumo das funções com maior tempo acumulado, produzido por `cProfile`. |
| `deep` | Inclui o perfil de funções e um resumo das linhas do script alvo com maior tempo de parede acumulado. |

Os resumos mostram até 20 entradas. Funções dentro de extensões nativas não são divididas em chamadas Python menores pelo `cProfile`. No perfil por linha, o tempo de uma linha inclui o tempo de parede gasto em chamadas iniciadas naquela linha; o tracing aumenta o overhead da execução.

## Consultar o histórico: `history`

```text
pylens history [--limit <quantidade>] [--database <caminho>]
```

Mostra execuções recentes, começando pelas mais novas. `--limit` controla quantas linhas aparecem (padrão `20`) e precisa ser maior que zero. `--database` aponta para o mesmo arquivo local em que o histórico foi salvo.

```bash
pylens history
pylens history --limit 5 --database ./historico.sqlite3
```

Cada linha apresenta o ID, início, status, classificação, duração e caminho do script. O ID identifica uma execução para comandos posteriores.

## Consultar os logs: `logs`

```text
pylens logs <execution_id> [--detail lite|normal|deep] [--database <caminho>]
```

Mostra os eventos estruturados que o PyLens gravou para aquela execução. `--detail` escolhe a quantidade de informação: `lite` mostra horário/tempo decorrido e tipo do evento; `normal` (padrão) acrescenta nível e mensagem; `deep` também imprime os detalhes em JSON.

```bash
pylens logs 3
pylens logs 3 --detail lite
pylens logs 3 --detail deep --database ./historico.sqlite3
```

Esses logs contêm eventos do PyLens, como limites atingidos, erros e motivos da classificação. Eles não incluem o texto de `stdout` e `stderr` do script.

## Excluir uma execução: `delete`

```text
pylens delete <execution_id> [--database <caminho>] [--yes]
```

`<execution_id>` é o ID numérico mostrado pelo histórico. Por padrão, o PyLens pede confirmação; `--yes` pula a pergunta. A exclusão remove a execução e, por chave estrangeira, suas amostras e eventos associados. Execuções ainda em andamento não podem ser excluídas.

```bash
pylens delete 3
pylens delete 3 --yes --database ./historico.sqlite3
```

## Códigos de saída da CLI

O código de saída informa ao terminal ou a outro programa como a operação terminou:

| Código | Significado |
| --- | --- |
| `0` | Execução concluída, consulta bem-sucedida ou exclusão cancelada. |
| `1` | Script falhou, execução inexistente ou não pôde ser excluída (por exemplo, ID ainda em andamento). |
| `2` | Argumentos inválidos ou erro de configuração, banco ou sistema. |
| `124` | Timeout atingido. |
| `125` | Limite de CPU atingido. |
| `130` | Execução interrompida pelo usuário. |
| `137` | Limite de memória atingido. |

Quando o script falha com um código próprio, a CLI devolve esse código; se ele for zero apesar do estado de falha, devolve `1`.

## Argumentos do exemplo

O exemplo `examples/sample_workload.py` aceita:

```text
--seconds <número>
```

Define por quantos segundos a carga de CPU roda. O padrão é `2`; o valor precisa ser maior que zero e no máximo `15`.

```bash
pylens run examples/sample_workload.py -- --seconds 1.5
```

## Sintaxe Python usada nas APIs

Os fragmentos a seguir mostram as formas públicas mais úteis para integração Python. `str`, `int`, `float`, `Path`, `Optional` e `Sequence` são anotações de tipo: documentam o tipo esperado ou devolvido, mas não alteram por si só a execução do Python.

### `Settings`

```python
from pathlib import Path
from pylens.config.settings import Settings

settings = Settings(
    mode="normal",
    timeout_seconds=120,
    memory_limit_bytes=2 * 1024**3,
    cpu_limit_percent=100,
    database_path=Path("./historico.sqlite3"),
)
```

`Settings` agrupa as configurações. `cpu_limit_percent` limita a CPU agregada observada na árvore de processos; o padrão `100` corresponde a um núcleo lógico totalmente ocupado. `database_path=None` seleciona `~/.pylens/history.sqlite3`. A classe valida modo e limites ao ser criada. `sample_interval_seconds` informa o intervalo de coleta correspondente ao modo, e `effective_database_path` devolve o caminho efetivo expandindo `~`.

### `run_script`

```python
from pylens.core.executor import run_script

resultado = run_script(
    "tarefa.py",
    ["--entrada", "dados.csv"],
    settings=settings,
    working_directory="./projeto",
)
```

O primeiro argumento é o caminho do script; o segundo é uma sequência de argumentos repassados a ele. `settings` e `working_directory` são opcionais e nomeados por causa do `*` na assinatura. O resultado é um `RunResult`, com ID, status, classificação, código de saída, duração, saídas do processo e, quando disponível, resumo do perfil.

### Tipos de amostra e resultados

`ProcessSample` é uma dataclass imutável com `cpu_percent`, memória RSS e VMS, RSS dos filhos, quantidade de threads e quantidade de processos. As medidas podem ser `None` quando a árvore não foi observada por completo. `process_tree_complete` indica se a amostra foi completa.

`RunResult` também é uma dataclass imutável. Seus campos centrais são `execution_id`, `status`, `classification`, `exit_code` e `duration_seconds`; `stdout`, `stderr` e `profile_summary` contêm texto capturado. `profile_summary` pode ser `None` fora dos modos que perfilam funções ou se o perfil não ficou disponível.

`classification_reasons` contém os motivos da classificação. `NORMAL` indica conclusão bem-sucedida sem sinais de atenção; `WARNING` indica uso acima de 80% de algum limite, medições incompletas, interrupção pelo usuário ou saída em `stderr`; `CRITICAL` indica falha, erro interno, timeout ou limite de CPU/memória atingido. `UNDETERMINED` é usado quando faltam dados suficientes. Os motivos também são salvos como evento `EXECUTION_CLASSIFIED` no histórico.

## Sintaxe do banco SQLite

O arquivo `src/pylens/database/database.sql` cria três tabelas. `CREATE TABLE IF NOT EXISTS` cria cada tabela apenas se ela ainda não existir. `INTEGER`, `TEXT` e `REAL` descrevem classes de valores; `NOT NULL` exige um valor; `DEFAULT` define um valor inicial; `CHECK` rejeita valores fora de uma condição.

### `executions`

Guarda uma linha por execução: `id` é a chave primária; `script_path`, argumentos em JSON, modo, horários, status e configuração descrevem a execução. `pid`, duração, código de saída e resumo de erro podem ficar sem valor enquanto ainda não são conhecidos. As validações limitam os modos a `normal`, `detailed` e `deep`, os status aos estados implementados e as classificações a `NORMAL`, `WARNING`, `CRITICAL` ou `UNDETERMINED`.

### `samples`

Guarda medições ligadas a uma execução por `execution_id`. Tempo decorrido, CPU, RSS, VMS, memória dos filhos e contagens são valores da amostra; métricas podem ser `NULL` quando não puderam ser medidas. `UNIQUE (execution_id, elapsed_ms)` impede duas amostras no mesmo instante lógico para uma execução.

### `logs`

Guarda eventos com horário, nível (`DEBUG`, `INFO`, `WARNING` ou `ERROR`), tipo, mensagem e detalhes em JSON. `elapsed_ms` é opcional, pois alguns eventos não correspondem a um ponto de medição.

Nas duas tabelas relacionadas, `FOREIGN KEY ... REFERENCES executions(id)` exige uma execução válida. `ON DELETE CASCADE` apaga as amostras e logs quando a execução pai é removida. `CREATE INDEX` cria índices para acelerar consultas por execução e horário; eles não mudam o significado dos dados.

## Menu interativo legado

O pacote `src/pylens/interface/` contém a CLI principal do projeto. Tanto `pylens` quanto `python -m pylens` iniciam essa mesma interface e aceitam os comandos documentados acima.
