# Applicazione per la conversione di file SQL Server in MySQL
Questa applicazione si occupa di convertire dei file SQL Server passati in input come argomento, in file MySQL. 

## Flag 
- -b, --bulk-mode - elabora come file sorgente tutti i file presenti (esclude -s e -t) nella cartella utilizzata per i file sorgente. I file destinazione avranno come prefisso "{nomefile_sorgente}_d.sql".
- -s - file sorgente (obbligatorio);
- -t - file target (obbligatorio);
- -c, --clean - pulisci statement come: use "nome-vecchio-db";
- -g - genera tabelle ricavando struttura dal file sorgente (questo comando esclude -i)
- -i - genera solo query di insert senza generare le tabelle (questo comando esclude -g)
- -f, --config - percorso a un file di configurazione custom (default: ~/.config/dconv/config.json)
- -h, --help, genera testo di help

## Linguaggio
Questa applicazione è scritta in Python e deve essere compilata per generare un eseguibile che giri su tutte le Piattaforme Unix-like.

## Dipendenze
Questa applicazione non ha dipendenze runtime e non dovrà mai averne, compiendo solo variazioni su stringhe e testi.
Per la compilazione viene usato **PyInstaller** (installato automaticamente da `build.sh`).

## File principali
- `dconv.py` — script principale (tutto in un file, nessuna dipendenza)
- `build.sh` — script di build; genera `dist/dconv` (eseguibile standalone)
- `sample/` — file SQL Server di esempio per test

## Dettagli tecnici
- Input: UTF-16 con BOM (tipico export SQL Server), UTF-8 BOM, o UTF-8 plain
- Output: sempre UTF-8 senza BOM
- Trasformazioni applicate sempre: rimozione `GO`, `SET IDENTITY_INSERT`, `[dbo].` prefix, `[name]` → `` `name` ``, `N'...'` → `'...'`, `INSERT` → `INSERT INTO`, aggiunta `;` finale
- Trasformazioni opzionali: rimozione `USE [db]` (`-c`), generazione `CREATE TABLE` (`-g`)
- `-g` e `-i` sono mutuamente esclusivi; il default (nessuno dei due) equivale a `-i`

## File di configurazione
dconv cerca `~/.config/dconv/config.json` (o `$XDG_CONFIG_HOME/dconv/config.json`) per personalizzazioni per-database.

### Struttura
```json
{
  "databases": {
    "NomeDB": {
      "tables": {
        "NomeTabella": {
          "extra_columns": [
            { "name": "ColName", "definition": "INT GENERATED ALWAYS AS (...) VIRTUAL" }
          ]
        }
      }
    }
  },
  "default": { "tables": { } }
}
```

### Logica di lookup
1. Match esatto su nome DB estratto da `USE [...]` nel dump
2. Match per sottostringa: chiave di `databases` contenuta nel nome del file sorgente
3. Fallback su blocco `default` (se presente)

### Comportamento
- Le `extra_columns` vengono appese in coda al file generato come `ALTER TABLE ... ADD COLUMN`
- Senza file di configurazione, il comportamento è invariato
