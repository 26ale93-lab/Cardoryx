CARDORYX v2.1.27 — LOCAL MEE 009–016 ASSETS

1. Upload the CONTENTS of this folder to the root of the Cardoryx repository.
2. GitHub Actions will run “Fetch Cardoryx MEE energy assets” and create:
   assets/energies/mee-009.jpg ... mee-016.jpg
3. After the workflow finishes and GitHub Pages redeploys, reload Cardoryx.

The index uses these local files FIRST for MEE 009–016.
Pricing, finish, Stamp/Edition, Play! Pokémon and Prize Pack logic are unchanged.

Why the workflow exists: this execution environment cannot currently resolve
archives.bulbagarden.net DNS, so the verified binaries cannot be placed in this
ZIP directly. GitHub's runner downloads them once into your repository; Safari
then loads only your own GitHub Pages local assets.
