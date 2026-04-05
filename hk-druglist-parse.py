import json
import os
import re
from typing import Any, Optional, cast

import requests
import xmlschema
from bs4 import BeautifulSoup
from bs4.element import Tag
import pdfplumber
from tqdm import tqdm

with open("routes.json", encoding="utf-8") as f:
    ROUTES: dict[str, list[str]] = json.load(f)

with open("forms.json", encoding="utf-8") as f:
    FORMS: dict[str, list[str]] = json.load(f)

with open("patches/tradename.json", encoding="utf-8") as f:
    TRADENAME_PATCHES: dict[str, str] = json.load(f)

with open("patches/ingredient_shorthands.json", encoding="utf-8") as f:
    INGREDIENT_SHORTHANDS: dict[str, str] = json.load(f)

with open("patches/company_override.json", encoding="utf-8") as f:
    COMPANY_OVERRIDE: dict[str, str] = json.load(f)

with open("patches/dosage_override.json", encoding="utf-8") as f:
    DOSAGE_OVERRIDE: dict[str, list[dict[str, Any]]] = json.load(f)

with open("patches/route_forms_override.json", encoding="utf-8") as f:
    ROUTE_FORMS_OVERRIDE: dict[str, dict[str, str]] = json.load(f)

with open("LegalClasses.json") as f:
    LEGAL_CLASSES: dict[str, str] = json.load(f)

with open("SaleRequirements.json") as f:
    SALE_REQUIREMENTS: dict[str, str] = json.load(f)

CONCENTRATION_UNITS_SPACE = ["% w/v", "% v/v", "% w/w"]
CONCENTRATION_UNITS = ["%w/v", "%v/v", "%w/w", "%"]

WEIGHT_UNITS = {
    "microgram": "mcg",
    "miligram": "mg",
    "gram": "g",
    "iu": "iu",
    "units": "units",
}

SOLVENTS = ["-", "alcohol", "ethanol", "stabilizer solution"]


def safe_get(lst: list[Any], index: int, default: Optional[str] = None):
    try:
        return lst[index]
    except IndexError:
        return default


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def match_active_ingredient(product_name: str, active_ings: list[str]) -> Optional[str]:
    for i in product_name.replace("&", " ").split():
        for j in active_ings:
            if i == j.lower().split()[0]:
                return j
    return None


amount_type = tuple[
    Optional[float], Optional[str], Optional[float], Optional[float], Optional[str]
]


def get_amount(product_name: str) -> amount_type:
    # weight_value, weight_unit, volume (in ml), concentration, concentration_unit
    weight_value, weight_unit, volume, concentration_value, concentration_unit = [
        None
    ] * 5
    for i in product_name.split():
        for j in WEIGHT_UNITS.values():
            if j in i:
                weight_unit = j
                weight_value_str = i.split(j)[0].replace(j, "")
                if is_number(weight_value_str):
                    weight_value = float(weight_value_str)
                    break
                else:
                    weight_unit = None
        for j in WEIGHT_UNITS.keys():
            if j in i:
                weight_unit = WEIGHT_UNITS[j]
                weight_value_str = i.split(j)[0].replace(j, "")
                if is_number(weight_value_str):
                    weight_value = float(weight_value_str)
                    break
                else:
                    weight_unit = None
        if i.endswith("ml"):
            volume_str = i.split("/")[-1]
            volume_str = volume_str.replace("ml", "")
            if volume_str == "":
                volume = float(1)
            elif is_number(volume_str):
                volume = float(volume_str)
        for j in CONCENTRATION_UNITS:
            if j in i:
                concentration_unit = j
                concentration_value_str = i.replace(j, "")
                if is_number(concentration_value_str):
                    concentration_value = float(concentration_value_str)
                    break
                else:
                    concentration_unit = None

    return weight_value, weight_unit, volume, concentration_value, concentration_unit


def get_compound_amount(product_name: str) -> list[amount_type]:
    result: list[amount_type] = []
    compound_amount_str = None
    for i in reversed(product_name.split()):
        if "/" not in i:
            continue

        test_str = i
        for j in (
            list(WEIGHT_UNITS.keys())
            + list(WEIGHT_UNITS.values())
            + CONCENTRATION_UNITS
            + [".", "/"]
        ):
            if j in test_str:
                test_str = test_str.replace(j, "")
        if test_str.isnumeric():
            compound_amount_str = i

    if compound_amount_str is None:
        return result

    def remove_slash_from_conc(s: str, rev: bool) -> str:
        for i in CONCENTRATION_UNITS:
            if rev:
                s = s.replace(i.replace("/", ""), i)
            else:
                s = s.replace(i, i.replace("/", ""))
        return s

    compound_amount_str = remove_slash_from_conc(compound_amount_str, False)

    last_str = compound_amount_str.split("/")[-1]
    _, weight_unit_last, _, _, concentration_unit_last = get_amount(
        remove_slash_from_conc(last_str, True)
    )
    if weight_unit_last is not None:
        unit_last = weight_unit_last
    elif concentration_unit_last is not None:
        unit_last = concentration_unit_last
    else:
        return result

    for i in compound_amount_str.split("/"):
        if is_number(i):
            i = i + unit_last
        result.append(get_amount(remove_slash_from_conc(i, True)))
    return result


def cleanup_product_name(product_name: str) -> str:
    name_clean = product_name
    for k, v in TRADENAME_PATCHES.items():
        name_clean = name_clean.replace(k, v)
    name_clean = " " + name_clean.replace("/", "*slash*").replace("&", "*amp*") + " "
    for i in INGREDIENT_SHORTHANDS.keys():
        for pre, post in ((" ", " "), ("*", " "), (" ", "*"), ("*", "*")):
            name_clean = name_clean.replace(
                pre + i + post, pre + INGREDIENT_SHORTHANDS[i] + post
            )
    name_clean = name_clean.replace("*slash*", "/").replace("*amp*", "&").strip()

    name_clean = name_clean.lower()
    for i in CONCENTRATION_UNITS_SPACE:
        name_clean = name_clean.replace(i, i.replace(" ", ""))
    name_clean = name_clean.replace("apo-", "apo ")
    name_clean = name_clean.replace("-", "&")

    name_split = name_clean.split()
    name_clean = ""
    prev_is_number = False
    for i in name_split:
        if "%" in i or "ml" in i:
            if prev_is_number and (name_clean == "" or name_clean[-1] == " "):
                name_clean = name_clean[:-1]
            name_clean += i + " "
        elif (
            i == WEIGHT_UNITS.keys()
            or i == WEIGHT_UNITS.values()
            or (
                (
                    any(j in WEIGHT_UNITS.keys() for j in i)
                    or any(j in WEIGHT_UNITS.values() for j in i)
                )
                and i.endswith("/")
            )
            or any(i == j + "s" for j in WEIGHT_UNITS.keys())
        ):
            if name_clean == "" or name_clean[-1] == " ":
                name_clean = name_clean[:-1]
            name_clean += i + " "
        elif i in ("/", "&") or i == "and" or i == "with":
            if name_clean[-1] == " ":
                name_clean = name_clean[:-1]
            if i in ("and", "with"):
                name_clean += "&"  # Don't add space at back
            else:
                name_clean += i  # Don't add space at back
        else:
            name_clean += i + " "

        if is_number(i):
            prev_is_number = True
        else:
            prev_is_number = False

    return name_clean.strip()


def get_route_form(
    product_name: str, route_form_list: dict[str, list[str]]
) -> Optional[str]:
    for route, words_list in route_form_list.items():
        for words in words_list:
            pattern = (
                "\\b"
                + "\\b.*?\\b".join([re.escape(i) for i in words.split(" ")])
                + "\\b"
            )
            if re.search(
                pattern, product_name.lower().replace("-", " ").replace(".", "")
            ):
                return route
    return None


def split_product_name_to_ingredients(product_name: str) -> Optional[list[str]]:
    if "&" in product_name:
        return product_name.split("&")
    elif "/" in product_name:
        for i in CONCENTRATION_UNITS:
            product_name = product_name.replace(i, i.replace("/", "*slash*"))
        a = []
        for i in product_name.split():
            if any(j.isnumeric() for j in i):
                i = i.replace("/", "*slash*")
            a.append(i)
        " ".join(a)
        product_name_ingredients = product_name.split("/")
        return [i.replace("*slash*", "/") for i in product_name_ingredients]

    return None


def get_company_name_to_lic_dict(
    companies: dict[str, dict[str, str]],
) -> dict[str, str]:
    return {v["companyName"]: k for k, v in companies.items()}


def parse_company() -> dict[str, dict[str, str]]:
    companies: dict[str, dict[str, str]] = {}
    lic_types = ("2A", "7A", "ML")
    for lic_type in lic_types:
        r = requests.get(
            f"https://www.drugoffice.gov.hk/eps/licList?licType={lic_type}&displayRange=all"
        )
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", id="table_data")
        assert isinstance(table, Tag)
        for i in cast(list[Tag], table.find_all("tr")[2:]):
            info = cast(list[Tag], i.find_all("td"))
            license_no = info[1].text
            company_name_en_tag = info[3].find("span", {"class": "busName"})
            if isinstance(company_name_en_tag, Tag):
                company_name_en = company_name_en_tag.text
            else:
                company_name_en = ""
            company_name_tc_tag = info[3].find("span", {"class": "busNameChn"})
            if isinstance(company_name_tc_tag, Tag):
                company_name_tc = (
                    company_name_tc_tag.text
                    if company_name_tc_tag.text != "未有登記中文名稱"
                    else ""
                )
            else:
                company_name_tc = ""
            company_address = info[5].text
            if len(info) >= 7:
                license_expire = info[7].text
            else:
                license_expire = ""

            companies[license_no] = {
                "companyName": company_name_en,
                "companyNameTC": company_name_tc,
                "companyAddress": company_address,
                "licenseExpire": license_expire,
            }

    with open("output/companies.json", "w+", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=4)

    return companies


def parse_compendium() -> list[dict[str, Any]]:
    hlines = [20, 45, 560]
    vlines = [17, 155, 375, 465, 770, 820]
    result: list[dict[str, Any]] = []

    with pdfplumber.open("Compendium.pdf") as pdf:
        for page in tqdm(pdf.pages[7:]):
            # im = page.to_image()
            # im.draw_hlines(hlines)
            # im.draw_vlines(vlines)
            # im.save("out.png")
            # exit()
            table = cast(list[str], page.extract_table({
                "vertical_strategy": "explicit",
                "horizontal_strategy": "lines",
                "explicit_horizontal_lines": hlines,
                "explicit_vertical_lines": vlines,
            }))
            for row in table:
                if row[0].startswith("Product Name"):
                    continue
                name = " ".join(row[0].split("\n")[:-1])
                permit_no = row[0].split("\n")[-1].replace("(", "").replace(")", "")
                company = row[1].split("\n")[0]
                company_address = " ".join(row[1].split("\n")[1:])
                sale_req = row[2].split("\n")[0]
                legal_class = row[2].split("\n")[1].replace("(", "").replace(")", "")
                active_ings = row[3].replace("\n"," ").split(", ")
                reg_date = row[4]

                result.append({
                    "name": name,
                    "permitNo": permit_no,
                    "company": company,
                    "companyAddress": company_address,
                    "saleReq": sale_req,
                    "legalClass": legal_class,
                    "activeIngs": active_ings,
                    "regDate": reg_date,
                })

    with open("output/compendium.json", "w+", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
    
    return result

def get_compendium_online(permit_no: str) -> dict[str, Any]:
    print(f"Query {permit_no}")
    data = {
        'keywordForSorting': '',
        'orderBy': '',
        'orderType': '',
        'hkNoFrom': '',
        'hkNoTo': permit_no.split("-")[-1],
        'productName': '',
        'activeIngTextSearchType': 'A',
        'activeIngTexts[0]': '',
        'activeIngTexts[1]': '',
        'activeIngTexts[2]': '',
        'certHolder': '',
        'perPage': '20',
        'searchType': 'A',
        'pageNoRequested': '1',
        'userType': 'E',
        'fromLang': 'tc',
        'fromSection': 'healthcare_providers',
        'btn_01': '搜索',
    }

    response = requests.post(
        'https://www.drugoffice.gov.hk/eps/drug/productSearchOneFieldAction',
        data=data,
    )

    soup = BeautifulSoup(response.text, "html.parser")
    result_tag = soup.find("table", {"class": "table_database"}).find("tbody").find_all("tr")[-1]  # type: ignore
    product_detail_page = f"https://www.drugoffice.gov.hk/eps/drug/{result_tag.find('a')['href']}"

    response = requests.get(product_detail_page)
    soup = BeautifulSoup(response.text, "html.parser")
    table_row_tags = soup.find("tr", {"class": "content_text01"}).find("table").find("table").find_all("tr", recursive=False)  # type: ignore

    return {
        "name": table_row_tags[2].find_all("td")[2].text.strip(),
        "permitNo": table_row_tags[3].find_all("td")[2].text.strip(),
        "company": table_row_tags[4].find_all("td")[2].text.strip(),
        "companyAddress": table_row_tags[5].find_all("td")[2].text.strip(),
        "saleReq": [k for k, v in SALE_REQUIREMENTS.items() if v in table_row_tags[7].find_all("td")[2].text.strip()][0],
        "legalClass": [k for k, v in LEGAL_CLASSES.items() if v == table_row_tags[6].find_all("td")[2].text.strip()][0],
        "activeIngs": [i.text.strip() for i in table_row_tags[8].find_all("td")[2].find("tbody").find_all("td") if i.text],
        "regDate": table_row_tags[9].find_all("td")[2].text.strip(),
    }

def get_compendium(compendium: list[dict[str, Any]], permit_no: str) -> dict[str, Any]:
    match = [i for i in compendium if i["permitNo"] == permit_no]
    if len(match) == 0:
        # pdf compendium may not have newest drugs
        return get_compendium_online(permit_no)
    else:
        return match[0]

def main() -> None:
    if os.path.isdir("output") is False:
        os.mkdir("output")

    if "DrugList.xsd" not in os.listdir():
        r = requests.get("https://www.drugoffice.gov.hk/eps/psi/DrugList.xsd")
        with open("DrugList.xsd", "w+", encoding="utf-8") as f:
            f.write(r.text)
    if "DrugList.xml" not in os.listdir():
        r = requests.get("https://www.drugoffice.gov.hk/eps/psi/DrugList.xml")
        with open("DrugList.xml", "w+", encoding="utf-8") as f:
            f.write(r.text)
    if "Compendium.pdf" not in os.listdir():
        r = requests.get("https://www.ppbhk.org.hk/eng/doc/Compendium.pdf")
        with open("Compendium.pdf", "wb+") as f:
            f.write(r.content)
    if "compendium.json" not in os.listdir("output"):
        compendium = parse_compendium()
    else:
        with open("output/compendium.json", "r", encoding="utf-8") as f:
            compendium = cast(list[dict[str, Any]], json.load(f))

    if "companies.json" not in os.listdir("output"):
        companies = parse_company()
    else:
        with open("output/companies.json", encoding="utf-8") as f:
            companies = json.load(f)
    company_name_to_lic_dict = get_company_name_to_lic_dict(companies)

    schema = xmlschema.XMLSchema("DrugList.xsd")
    drug_dict = cast(dict[str, Any], schema.to_dict("DrugList.xml"))

    # print(drug_dict)
    # with open("DrugList.json", "w+", encoding="utf-8") as f:
    #     json.dump(drug_dict, f, ensure_ascii=False, indent=4)

    drug_dict_new: list[dict[str, Any]] = []

    patch_needed_route: list[tuple[str, str]] = []
    patch_needed_form: list[tuple[str, str]] = []
    patch_needed_dosage: list[tuple[str, str]] = []
    patch_needed_company: list[str] = []
    for drug in drug_dict["drug"]:
        product_name: str = drug["productName"]
        reg_cert_holder_name: str = drug["regCertHolderName"]
        permit_no: str = drug["permitNo"]
        active_ings: list[str] = drug["activeIngs"]["activeIng"]
        cleaned_name = cleanup_product_name(product_name)
        is_vet = product_name[-1] == "(VET)"
        route: Optional[str] = get_route_form(product_name, ROUTES)
        form: Optional[str] = get_route_form(product_name, FORMS)
        active_ing_solvent = []
        for solvent in SOLVENTS:
            if solvent in active_ings:
                active_ing_solvent.append(solvent)
                active_ings.remove(solvent)

        product_name_ingredients = None
        if len(active_ings) > 1:
            product_name_ingredients = split_product_name_to_ingredients(cleaned_name)
        if not (
            product_name_ingredients
            and len(product_name_ingredients) == len(active_ings)
        ):
            product_name_ingredients = None

        if route is None:
            patch_needed_route.append((permit_no, product_name))
        if form is None:
            patch_needed_form.append((permit_no, product_name))

        active_ings_new: dict[str, dict[str, Any]] = {}
        for solvent in active_ing_solvent:
            active_ings_new[solvent] = {}

        if product_name_ingredients is None:
            if len(active_ings) == 1:
                (
                    weight_value,
                    weight_unit,
                    volume,
                    concentration_value,
                    concentration_unit,
                ) = get_amount(cleaned_name)
                active_ings_new[active_ings[0]] = {
                    "weightValue": weight_value,
                    "weightUnit": weight_unit,
                    "volume": volume,
                    "concentrationValue": concentration_value,
                    "concentrationUnit": concentration_unit,
                }
            else:
                for i in active_ings:
                    active_ings_new[i] = {}
            if (
                any(char.isdigit() for char in cleaned_name)
                and get_amount(cleaned_name) == [None] * 5
            ):
                patch_needed_dosage.append((permit_no, product_name))
        else:
            compound_amount = get_compound_amount(cleaned_name)
            active_ings_matched: list[tuple[str, str]] = []
            for product_name_frag in product_name_ingredients:
                active_ing = match_active_ingredient(product_name_frag, active_ings)
                if active_ing is not None:
                    active_ings_matched.append((active_ing, product_name_frag))
            for idx, (active_ing, product_name_frag) in enumerate(active_ings_matched):
                if len(compound_amount) > 0 and len(active_ings_matched) == len(
                    compound_amount
                ):
                    active_ings_new[active_ing] = {
                        "weightValue": compound_amount[idx][0],
                        "weightUnit": compound_amount[idx][1],
                        "volume": compound_amount[idx][2],
                        "concentrationValue": compound_amount[idx][3],
                        "concentrationUnit": compound_amount[idx][4],
                    }
                else:
                    (
                        weight_value,
                        weight_unit,
                        volume,
                        concentration_value,
                        concentration_unit,
                    ) = get_amount(product_name_frag)
                    active_ings_new[active_ing] = {
                        "weightValue": weight_value,
                        "weightUnit": weight_unit,
                        "volume": volume,
                        "concentrationValue": concentration_value,
                        "concentrationUnit": concentration_unit,
                    }

            patch_needed_dosage_added = False
            for i in active_ings:
                if i not in [i[0] for i in active_ings_matched]:
                    active_ings_new[i] = {}
                    if (
                        any(char.isdigit() for char in cleaned_name)
                        and patch_needed_dosage_added is False
                    ):
                        patch_needed_dosage.append((permit_no, product_name))
                        patch_needed_dosage_added = True

        # if reg_cert_holder_name in COMPANY_OVERRIDE:
        #     company_lic_no = company_name_to_lic_dict.get(COMPANY_OVERRIDE[reg_cert_holder_name])
        if reg_cert_holder_name in company_name_to_lic_dict:
            company_lic_no = company_name_to_lic_dict.get(reg_cert_holder_name)
        else:
            for pos in range(0, 3):
                candidates = [
                    i
                    for i in company_name_to_lic_dict
                    if safe_get(reg_cert_holder_name.split(), pos, "1")
                    == safe_get(i.split(), pos, "2")
                ]
                if len(candidates) == 1:
                    company_lic_no = candidates[0]
                    break
                else:
                    company_lic_no = None
        if company_lic_no is None and reg_cert_holder_name not in patch_needed_company:
            patch_needed_company.append(reg_cert_holder_name)

        matched_compendium = get_compendium(compendium, permit_no)

        drug_dict_new.append(
            {
                "productName": product_name,
                "regCertHolderName": reg_cert_holder_name,
                "companyLicenseNo": company_lic_no,
                "permitNo": permit_no,
                "isVet": is_vet,
                "saleReq": matched_compendium["saleReq"],
                "legalClass": matched_compendium["legalClass"],
                "regDate": matched_compendium["regDate"],
                "route": route
                if permit_no not in ROUTE_FORMS_OVERRIDE
                else ROUTE_FORMS_OVERRIDE[permit_no]["route"],
                "form": form
                if permit_no not in ROUTE_FORMS_OVERRIDE
                else ROUTE_FORMS_OVERRIDE[permit_no]["form"],
                "activeIngs": [
                    {
                        "activeIng": k,
                        "dosage": {
                            i: v.get(i)
                            for i in (
                                "weightValue",
                                "weightUnit",
                                "volume",
                                "concentrationValue",
                                "concentrationUnit",
                            )
                            if v.get(i) is not None
                        },
                    }
                    for k, v in active_ings_new.items()
                ]
                if permit_no not in DOSAGE_OVERRIDE
                else DOSAGE_OVERRIDE[permit_no],
            }
        )

    with open("output/DrugList.json", "w+", encoding="utf-8") as f:
        json.dump(drug_dict_new, f, ensure_ascii=False, indent=4)

    with open("output/patch_needed_route.txt", "w+", encoding="utf-8") as f:
        for i, j in patch_needed_route:
            f.write(f"{i} {j}\n")

    with open("output/patch_needed_form.txt", "w+", encoding="utf-8") as f:
        for i, j in patch_needed_form:
            f.write(f"{i} {j}\n")

    with open("output/patch_needed_dosage.txt", "w+", encoding="utf-8") as f:
        for i, j in patch_needed_dosage:
            f.write(f"{i} {j}\n")

    with open("output/patch_needed_company.txt", "w+", encoding="utf-8") as f:
        for i in patch_needed_company:
            f.write(f"{i}\n")


if __name__ == "__main__":
    main()
