# Continent → subcontinents
continent_map = {
    "eurasia": ["europe", "asia"],
}

# Subcontinent → superregions → regions
superregion_map = {
    "europe": {
        "italy": [
            "central_italy_region",
            "magna_graecia_region",
            "cisalpine_gaul_region",
        ],
        "germany": [
            "belgica_region",
            "germania_region",
            "germania_superior_region",
            "rhaetia_region",
            "bohemia_area",
        ],
        "france": [
            "transalpine_gaul_region",
            "central_gaul_region",
            "armorica_region",
            "aquitaine_region",
        ],
        "iberia": [
            "lusitania_region",
            "tarraconensis_region",
            "baetica_region",
            "contestania_region",
        ],
        "britain": [
            "britain_region",
            "caledonia_region",
        ],
        "north_sea": [
            "scandinavia_region",
            "baltic_sea_region",
            "atlantic_region",
        ],
        "balkans": [
            "greece_region",
            "macedonia_region",
            "illyria_region",
            "albania_region",
            "thrace_region",
            "moesia_region",
        ],
        "eastern_europe": [
            "dacia_region",
            "sarmatia_europea_region",
            "vistulia_region",
            "venedia_region",
            "pannonia_region",
        ],
    },
    "asia": {
        "anatolia": [
            "asia_region",
            "bithynia_region",
            "galatia_region",
            "cappadocia_region",
            "cappadocia_pontica_region",
            "cilicia_region",
        ],
        "middle_east": [
            "taurica_region",
            "sarmatia_asiatica_region",
            "assyria_region",
            "mesopotamia_region",
            "gedrosia_region",
            "persis_region",
            "media_region",
            "bactriana_region",
            "ariana_region",
            "parthia_region",
            "syria_region",
            "palestine_region",
            "arabia_region",
            "arabia_felix_region",
        ],
        "india": [
            "gandhara_region",
            "maru_region",
            "avanti_region",
            "madhyadesa_region",
            "pracya_region",
            "vindhyaprstha_region",
            "dravida_region",
            "aparanta_region",
            "karnata_region",
        ],
        "central_asia": [
            "tibet_region",
            "himalayan_region",
            "sogdiana_region",
        ],
    },
}
