# dconv

CLI tool per la conversione di file SQL Server in sintassi MySQL compatibile.

Legge file esportati da SQL Server (tipicamente in UTF-16 con BOM) e produce file MySQL in UTF-8, applicando automaticamente tutte le trasformazioni necessarie: rimozione dei batch separator `GO`, conversione della notazione `[dbo].[Tabella]` in backtick, rimozione del prefisso `N'...'` dai valori Unicode e altro ancora.

---

## Requisiti

- Python 3.8+
- Nessuna dipendenza runtime

Per compilare l'eseguibile standalone è necessario avere `pip` disponibile (PyInstaller viene installato automaticamente in un virtualenv isolato).

---

## Installazione

### Opzione 1 — Eseguibile standalone (consigliato)

```bash
git clone https://github.com/tuo-utente/dconv.git
cd dconv
./build.sh
```

L'eseguibile viene generato in `dist/dconv`. Puoi copiarlo in una cartella nel tuo `$PATH`:

```bash
cp dist/dconv /usr/local/bin/
```

### Opzione 2 — Script Python diretto

```bash
python3 dconv.py -s sorgente.sql -t output.sql
```

---

## Compilazione multi-piattaforma

> **Importante:** PyInstaller non supporta la cross-compilazione. Per ottenere un eseguibile per una certa piattaforma è necessario eseguire `build.sh` **sulla piattaforma di destinazione**.

### Linux (x86_64 / ARM)

```bash
./build.sh
# Output: dist/dconv
```

### macOS

```bash
./build.sh
# Output: dist/dconv
```

Su macOS Apple Silicon (M1/M2) l'eseguibile generato sarà nativo `arm64`. Per produrre un binario universale (arm64 + x86_64) è necessario aggiungere il flag `--target-arch universal2` allo script:

```bash
python3 -m PyInstaller --onefile --target-arch universal2 --name dconv dconv.py
```

### Tramite Docker (build Linux da macOS o Windows)

Se non si dispone di una macchina Linux, è possibile compilare per Linux usando Docker:

```bash
docker run --rm -v "$(pwd)":/app -w /app python:3.11-slim bash -c "
  pip install --quiet pyinstaller &&
  pyinstaller --onefile --name dconv dconv.py
"
# Output: dist/dconv  (ELF binario Linux)
```

### Riepilogo compatibilità

| Piattaforma | Comando | Output |
|-------------|---------|--------|
| Linux x86_64 | `./build.sh` | `dist/dconv` (ELF) |
| Linux ARM64 | `./build.sh` | `dist/dconv` (ELF) |
| macOS x86_64 | `./build.sh` | `dist/dconv` (Mach-O) |
| macOS ARM64 | `./build.sh` | `dist/dconv` (Mach-O) |
| Linux (da Docker) | vedi sopra | `dist/dconv` (ELF) |

---

## Utilizzo

```
dconv -s <sorgente> -t <target> [opzioni]
dconv -b [opzioni]
```

### Flag

| Flag | Descrizione |
|------|-------------|
| `-s SOURCE` | File sorgente SQL Server (obbligatorio senza `-b`) |
| `-t TARGET` | File di output MySQL (obbligatorio senza `-b`) |
| `-b`, `--bulk-mode` | Elabora tutti i file `.sql` nella directory corrente; i file di output vengono nominati `<nomefile>_d.sql` |
| `-c`, `--clean` | Rimuove gli statement `USE [database]` |
| `-g` | Genera le istruzioni `CREATE TABLE` inferendo la struttura dagli INSERT (esclude `-i`) |
| `-i` | Genera solo gli INSERT senza `CREATE TABLE` (esclude `-g`) |
| `-f`, `--config` | Percorso a un file di configurazione custom (default: `~/.config/dconv/config.json`) |
| `-h`, `--help` | Mostra il testo di aiuto |

> **Nota:** `-g` e `-i` sono mutuamente esclusivi. Se non viene specificato né l'uno né l'altro, il comportamento è equivalente a `-i`.

---

## Esempi

Conversione base:
```bash
dconv -s export.sql -t output.sql
```

Conversione con pulizia dello statement `USE` e generazione delle tabelle:
```bash
dconv -s export.sql -t output.sql -c -g
```

Modalità bulk (tutti i `.sql` nella directory corrente):
```bash
dconv -b -c
```

Conversione con file di configurazione custom:
```bash
dconv -s export.sql -t output.sql -g -f /path/to/config.json
```

---

## File di configurazione

dconv supporta un file di configurazione JSON per applicare personalizzazioni per-database (es. aggiunta di colonne `VIRTUAL GENERATED` assenti dai dump).

### Posizione

Per default viene cercato in `~/.config/dconv/config.json` (o `$XDG_CONFIG_HOME/dconv/config.json`). È possibile specificare un percorso diverso con il flag `-f`:

```bash
dconv -s export.sql -t output.sql -g -f /path/to/config.json
```

### Struttura

```json
{
  "databases": {
    "NomeDB": {
      "tables": {
        "NomeTabella": {
          "extra_columns": [
            {
              "name": "NomeColonna",
              "definition": "INT GENERATED ALWAYS AS (`Anno` * 1000 + `Numero`) VIRTUAL"
            }
          ]
        }
      }
    }
  },
  "default": {
    "tables": {}
  }
}
```

### Logica di lookup del database

1. **Match esatto** — il nome del database viene estratto dallo statement `USE [NomeDB]` presente nel dump
2. **Match per sottostringa** — se non è presente `USE`, viene cercata una chiave di `databases` contenuta nel nome del file sorgente (es. la chiave `"MioDB"` matcha il file `MioDB_20260401.sql`)
3. **Fallback** — se nessun match viene trovato, viene usato il blocco `default` (se presente)

### Comportamento

- Le `extra_columns` vengono appese in coda al file generato come statement `ALTER TABLE ... ADD COLUMN`
- Senza file di configurazione il comportamento è invariato

---

## Trasformazioni applicate

| SQL Server | MySQL |
|------------|-------|
| `GO` | *(rimosso)* |
| `USE [database]` | *(rimosso con `-c`)* |
| `[dbo].[Tabella]` | `` `Tabella` `` |
| `[Colonna]` | `` `Colonna` `` |
| `N'stringa'` | `'stringa'` |
| `INSERT Tabella` | `INSERT INTO \`Tabella\`` |
| *(con `-g`)* | `CREATE TABLE IF NOT EXISTS ...` |

### Encoding
- **Input:** UTF-16 con BOM, UTF-8 con BOM, o UTF-8 plain
- **Output:** sempre UTF-8 senza BOM

---

## Licenza

MIT
