# Отметки выбранных100фото в исходной Googleтаблице

2026-10-11. STANDARD: явный запрос владельца добавить колонку в переданную таблицу
и отметить строки выбранных100фото. Это аннотация уже зафиксированного набора,
не изменениеscope/MLpermission/качества или frozeninventory.

На листе «На рассм-е» справа добавлена колонкаCI «В корпусе 100». Booleancheckboxes:
100checked, остальныеunchecked. У каждогоcheckedcell примечание сномером001–100
из [фиксированного списка](corpus-100-report.md). Headerstyle перенесён с соседней
колонки только дляnewheader, width150; исходные данные/formulas/validation не редактировались.

Сопоставление: source_row вacceptedSRC054 snapshot (SHA03b9cce1...) иexistingprepared
record. Служебныеproduct IDs присвоены подготовкойXLSX ивliveGoogleнет, поэтому
не использованы какliveключ. Checked100sourceRows дополнительно совпали поexact
competitorURL икатегории сoriginalsnapshot100/100. Rawsource records/fullfileID/URLs/
private paths остаютсятолькоprivateaudit, не врепозитории. Байт-сравнение embedded
Googleфото не выполнялось: подтверждена связьстрок систочником, не повторный imagehash.

Prewrite metadata/headers/identity checks; однаatomicbatch7requests: appendcolumn,
header/format/bodybool/note/BOOLEANvalidation/width. Затем полноеboundedreadback
новойколонки:100TRUE, missing/wrongvalues0, wrongvalidation0, wrongnumbernotes0;
100originalcompetitorlinks unchanged. Grid86→87columns;2740rows/frozen5 unchanged.
NativeGoogle render при100%: header иcheckboxes читаемы. Private700/600 audit сохранён
внеGit; corpus100/674inputs/manifest/nativejob/DB/sourceXLSX не изменялись.

Independentreview не проводилось (STANDARD); code/SDK/ML/build/query/publish отсутствуют.
НавыкиGoogleDrive/GoogleSheets применены дляexistingfileedit и проверкиmetadata/ranges.
