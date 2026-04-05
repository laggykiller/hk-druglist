Hong Kong List of Registered Pharmaceutical Products, with attempt to get route
e.g. `oral` (`route`), form e.g. `tablet` (`form`), active ingredient dosages (`dosage`)
and whether intended to be used on animal (`isVet`) by parsing
product name (`productName`).

Also combining Sale Requirement (`saleReq`), Legal classification (`legalClass`) and
Date of Registration (`regDate`) which is only available on inaccessible pdf file and
online database search that return one result at a time.

Generated list could be found at [output/DrugList.json](output/DrugList.json). Company
info is in [output/companies.json](output/companies.json), which you can search using
company license number (e.g. `40/2A/1987`)

No guarantee on accuracy of the generated file. Use at your own risk.

To generate:
```
pip install -r requirements.txt
python hk-druglist-parse.py
```

### Type info for `output/DrugList.json`
```typescript
interface DrugDosage {
  weightValue?: number;
  weightUnit?: 'g' | 'mg' | 'mcg' | 'iu' | 'unit';
  volume?: number;
  concentrationValue?: number;
  concentrationUnit?: '%w/v' | '%v/v' | '%w/w' | '%';
}

interface MedicationIngredient {
    activeIng: string,
    dosage: DrugDosage
}

interface Medication {
  productName: string;
  regCertHolderName: string;
  companyLicenseNo: string;
  permitNo: string;
  isVet: boolean;
  saleReq: 'POM' | 'P' | 'OTC';
  legalClass: 'A' | 'DDI' | 'DDI & A' | 'DDII&III' | 'DDII&III & A' | 'DDIV' | 'DDIV & A' | 'MA' | 'NP' | 'P1' | 'P1 & A' | 'P1 & DDI' | 'P1 & DDII&III' | 'P1 & DDIV' | 'P1, DDII&III & A' | 'P2' | 'P2 & A' | 'P2 & DDII&III' | 'P2 & DDIV' | 'P2, DDIV & A' | 'P1S1' | 'P1S1 & A' | 'P1S1 & DDI' | 'P1S1 & DDII&III' | 'P1S1, DDII&III & A' | 'P1S1S3' | 'P1S1S3 & A' | 'P1S1S3 & DDI' | 'P1S1S3 & DDII&III' | 'P1S1S3 & MA' | 'P1S1S3, DDII&III & A' | 'P1S3' | 'P1S3 & A';
  regDate: string;
  form: 'solution' | 'tablet' | 'capsule' | 'granules' | 'powder' | 'spray' | 'suppository' | 'enema' | 'inhalant' | 'nebuliser' | 'patch' | 'gel' | 'cream' | 'foam' | 'paste' | 'lotion' | 'ointment' | 'balm' | 'plaster' | 'shampoo' | 'chewing gum' | 'pessary' | 'gas';
  route: 'eye' | 'ear' | 'injection' | 'oral' | 'buccal' | 'rectal' | 'inhalation' | 'topical' | 'intraperitoneal' | 'vaginal';
  activeIngs: Array<MedicationIngredient>;
}
```

### Source
https://data.gov.hk/en-data/dataset/hk-dh-dh_do-hk-dh-do-pharmaceutical-product/resource/db148568-906e-4469-b4e7-e280955e0dc2
https://www.drugoffice.gov.hk/eps/psi/DrugList.xsd
https://www.drugoffice.gov.hk/eps/psi/DrugList.xml
https://www.drugoffice.gov.hk/eps/do/en/consumer/news_informations/relicList2.html?indextype=ML
https://www.drugoffice.gov.hk/eps/do/en/consumer/news_informations/relicList2.html?indextype=7A
https://www.drugoffice.gov.hk/eps/do/en/consumer/news_informations/relicList2.html?indextype=2A
https://www.ppbhk.org.hk/eng/doc/Compendium.pdf
https://www.drugoffice.gov.hk/eps/drug/productSearchOneFieldAction