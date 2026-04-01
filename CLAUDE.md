# Applicazione per la conversione di file SQL Server in MySQL
Questa applicazione si occupa di convertire dei file SQL Server passati in input come argomento, in file MySQL. 

## Flag 
- -b, --bulk-mode - elabora come file sorgente tutti i file presenti (esclude -s e -t) nella cartella utilizzata per i file sorgente. I file destinazione avranno come prefisso "{nomefile_sorgente}_d.sql".
- -s - file sorgente (obbligatorio);
- -t - file target (obbligatorio);
- -c, --clean - pulisci statement come: use "nome-vecchio-db";
- -g - genera tabelle ricavando struttura dal file sorgente (questo comando esclude -i)
- -i - genera solo query di insert senza generare le tabelle (questo comando esclude -g)
- -h, --help, genera testo di help

## Linguaggio
Questa applicazione è scritta in Python e deve essere compilata per generare un eseguibile che giri su tutte le Piattaforme Unix-like.

## Dipendenze
Questa applicazione non ha dipendenze e non dovrà mai averne, compiendo solo variazioni su stringhe e testi.
