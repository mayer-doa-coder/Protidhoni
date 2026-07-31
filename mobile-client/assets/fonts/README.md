# Bundled typefaces

Protidhoni uses the **Anek** multiscript family by Ek Type:

- `AnekBangla.ttf` for Bangla UI text.
- `AnekLatin.ttf` for English UI text.

Both source assets are unmodified variable TTF files from the official
[`EkType/Anek`](https://github.com/EkType/Anek) repository. Anek was designed
as a coordinated family across Bangla, Latin, and other Indic scripts, so the
two application languages retain a consistent visual hierarchy. The fonts are
licensed under the SIL Open Font License 1.1; see `OFL.txt`.

Android additionally contains `AnekBangla_bold.ttf` and
`AnekLatin_bold.ttf`. These are locally generated, unrenamed 700-weight,
100-width static instances of the corresponding variable fonts. React Native's
Android font manager explicitly looks for an `_bold` file at weights 700 and
above; the static instances prevent an otherwise silent fallback to the system
font. They remain covered by the same OFL 1.1 license.

Source files:

- `fonts/AnekBangla/variable/AnekBangla[wdth,wght].ttf`
- `fonts/AnekLatin/variable/AnekLatin[wdth,wght].ttf`
