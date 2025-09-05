# Caledonia 1874

This interactive tool lets users visualize and explore the migration patterns between different regions of German-speaking Prussia and the township of Caledonia in Waupaca County, Wisconsin.

## Background

I am a passonate genealogical hobbyist, and much of my family history runs through the Town of Caledonia and the surrounding areas. My research showed clear patterns of chain- and cluster-migration from Prussia to Caledonia in the 1850-1870s. As I started to complete my post-immigration tree, it occurred to me that a broader study of Caledonia might be a good lens for understanding the way a particular German-American community came together based on familial and regional ties in the Old Country.

## The data

I chose to work with the Caledonia section of an 1874 plat map of Waupaca County, sourced from the Wisconsin Historical Society. See https://explore.wishistory.org/asset-management/20HWMKM0GR9S?WS=SearchResults&Flat=FP and https://search.library.wisc.edu/catalog/9910104243602121. I chose this map because it's the earliest document I could find that gives a visual representation of my target community. German-speakers began to buy land in this area in the 1850s, and the majority of the German-speaking landowners in the 1874 map are immigrants. (A great book of plat maps from 1889 exists, but by then, many of the farms had been turned over to sons or otherwise sold off; this makes the migration chains harder to follow.)

The `caledonia.gramps` file in the `/data/` directory contains a minimal genealogical description of the individuals represented in the project. In order to link names on the 1874 map to known individuals, I cross-referenced between a number of sources, notably:

- 1870 and 1880 U.S. Federal Censuses, available on Ancestry.com
- Waupaca County land records, as available (and partially OCRed!) on FamilySearch
- Church books from the relevant Lutheran churches (St John's - now defunct; Zion Readfield; Immanuel in Zittau). These aren't publicly available - I have photographed and transcribed a large number of them myself.

Tying individuals to their home villages in Prussia is more complicated. The aforementioned churchbooks are a good start. Other sources include:

- Obituaries in WI newspapers on Newspapers.com, as well as New London newspapers available from the NLPL: http://rescarta.newlondonwi.org:8302/ResCarta-Web/jsp/RcWebBrowseCollections.jsp
- Naturalization and immigration records on Ancestry.com. Ships manifests out of Hamburg are particularly useful, as they sometimes mention home villages (even when they're garbled or illegible or incorrect, they are useful clues).
- Other general genealogical research tricks, such as jumping between siblings; tracking patterns of godparents in baptismal records; and so on.

I use https://www.meyersgaz.org/ to identify and standardize Prussian placenames and locations.

I've linked plats to individuals, individuals to each other, and individuals to Prussian places only when I've got a high degree of confidence - say, 80%+ - in the linkage.

## Limitations and known issues

The plat map represents land ownership. I'm less interested in land ownership than the community of people actually living on the farms. These often line up, but not always.

Where I couldn't nail down origins for a given individual, I've generally left the plat non-clickable. I've also ignored individuals who are known to be of non-Prussian origin.

## Tech overview

Genealogical data, including definitions of places and people, is built using the Gramps software. See https://gramps-project.org/ and the file at `data/caledonia.gramps`.

I georeferenced the Caledonia map and added parcel vectors using QGIS. See `data/qgis/` for `points` and other QGIS project files. I also used QGIS to build the image tiles, which are not kept in this repo due to size limitations.

Links between people and plats are manually curated in `associations.csv`.

Data is exported from Gramps and split into various app-friendly JSON files using a custom Python script, `scripts/export_from_gramps.py`.

A Bash script `scripts/build.sh` prepares assets for the web app.

Web interface uses Leaflet.js for map display.
