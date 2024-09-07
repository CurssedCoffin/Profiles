"""
Small script for convert ini template file to usable yaml file.
Only support [ruleset,custom_proxy_group] keys in ini files.
You need to write proxy-providers url manually.
"""

import urllib.parse
import os
import argparse
import requests
import tempfile
from loguru import logger

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

def download(url):
    logger.info(f"Downloading {url}")
    req = requests.get(url)
    with tempfile.NamedTemporaryFile(suffix="_" + os.path.basename(urllib.parse.urlparse(url).path), delete=False) as f:
        logger.success(f"Download success, save to {f.name}")
        f.write(req.content)
    return f.name

def yaml2dict(yaml_path):
    with open(yaml_path, "r", encoding="utf-8") as f:
        data: CommentedMap = yaml.load(f.read())
    return data

def dict2yaml(data: CommentedMap, yaml_path):
    dirname = os.path.dirname(yaml_path)
    if dirname not in ["", ".", ".."]:
        os.makedirs(dirname, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

def parse_ini(ini_path):
    with open(ini_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        lines = [x for x in lines if not (x.startswith(";") or x.startswith("[") or x.strip() == "")]

    rules = []
    rule_providers = {}
    # ruleset
    for line in lines:
        if line.startswith("ruleset"):
            line = line.split("=")[-1].strip()
            if "http" in line:
                group, url = line.split(",")
            else:
                group = line.split(",")[0]
                url = ",".join(line.split(",")[1:])
            
            if ",no-resolve" in url:
                url = url.replace(",no-resolve", "")
                group += ",no-resolve"
            if "http" in url:
                ruleset_name = os.path.splitext(os.path.basename(urllib.parse.urlparse(url).path))[0]
                rule = f"RULE-SET,{ruleset_name},{group}"
                if not (url.endswith(".list") or url.endswith(".yml") or url.endswith(".yaml")):
                    logger.error(f"Parse rule-provider [{ruleset_name}] error, invalid suffix for url: {url}, skip this rule")
                    continue
                rule_providers[ruleset_name] = {
                    "type": "http", # file http
                    "interval": 86400,
                    "behavior": "classical",
                    "format": "text" if url.endswith(".list") else "yaml",
                    "path": f"rules/{ruleset_name}.list" if url.endswith(".list") else f"rules/{ruleset_name}.yaml",
                    "url": url
                }
            else:
                rule = url.replace("[]", "")  
                if rule == "FINAL": rule = "MATCH"
                rule += "," + group
            
            rules.append(rule)
    
    groups = []
    # custom_proxy_group
    for line in lines:
        if line.startswith("custom_proxy_group"):
            line = line.split("=")[-1].strip()
            group = line.split("`")[0]
            if group not in groups:
                groups.append(group)
    groups += ["DIRECT", "REJECT"]
    
    proxy_groups = []
    # custom_proxy_group
    for line in lines:
        if line.startswith("custom_proxy_group"):
            line = line.split("=")[-1].strip()
            group = line.split("`")[0]
            
            line = line[len(group) + 1:]
            group_type = line.split("`")[0]
            line = line[len(group_type) + 1:]
            
            proxy_group = {
                "name": group,
                "type": group_type,
            }
            
            if group_type == "select":
                select_groups = [x.replace("[]", "") for x in line.split("`")]
                
                for select_group in select_groups:
                    if select_group not in groups: # is filter
                        if "filter" not in proxy_group: proxy_group["filter"] = ""
                        proxy_group["filter"] = select_group
                    else: # is group
                        if "proxies" not in proxy_group: proxy_group["proxies"] = []
                        proxy_group["proxies"].append(select_group)

            else:
                if group_type in ["url-test", "fallback", "load-balance"]:
                    proxxy_filter, speedtest_url, speedtest_param = line.split("`")
                    assert "http" in speedtest_url, f"invalid params for line: {line}"
                    
                    if group_type in ["url-test", "fallback"]: proxy_group["include-all"] = True
                    if group_type in ["load-balance"]: proxy_group["strategy"] = "consistent-hashing"
                    
                    proxy_group["filter"] = proxxy_filter
                    proxy_group["url"] = speedtest_url
                    proxy_group["interval"] = speedtest_param.split(",")[0]
                    proxy_group["tolerance"] = speedtest_param.split(",")[2]
                   
                else:
                    raise NotImplementedError(f"invalid group type {group_type}")
            
            if "proxies" not in proxy_group: proxy_group["include-all"] = True # fallback 
            proxy_groups.append(proxy_group)

    return rules, rule_providers, proxy_groups

def parse_yaml(rules, rule_providers, proxy_groups, yaml_path, dst_yaml_path):
    data = yaml2dict(yaml_path)
    if "proxies" in data:
        logger.warning("proxies in model yaml will be deleted.")
        del data["proxies"]
    if "proxy-groups" in data:
        logger.warning("proxy-groups in model yaml will be deleted.")
        del data["proxy-groups"]
    if "rules" in data:
        logger.warning("rules in model yaml will be deleted.")
        del data["rules"]
    if "proxy-providers" in data:
        logger.warning("proxy-providers in model yaml will be deleted.")
        del data["proxy-providers"]

    proxy_providers = {
        "provider1": {
            "type": "http",
            "interval": "3600",
            "health-check": {
                "enable": True,
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
            },
            "exclude-filter": "Traffic|Expire|Play|Game|官网|套餐|剩余",
            "url": ""
        },
    }
    data.insert(5, "proxy-providers", proxy_providers)

    data["rule-providers"] = rule_providers
    data["proxy-groups"] = proxy_groups
    data["rules"] = rules

    dict2yaml(data, dst_yaml_path)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--ini', default="https://mirror.ghproxy.com/https://raw.githubusercontent.com/CurssedCoffin/Profiles/main/Mihomo/ACL4SSR_Online_Full_AdblockPlus.ini", help="Input ini file path or url")
    parser.add_argument('-f', '--file', default="https://mirror.ghproxy.com/https://raw.githubusercontent.com/CurssedCoffin/Profiles/main/Mihomo/default.yaml", help="Model yaml file oath or url")
    parser.add_argument('-o', '--output', default="sub.yaml", help="Output yaml file oath")
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()

    ini_path = args.ini
    model_yaml_path = args.file
    output_path =args.output
    
    if ini_path.startswith("http"):
        logger.warning("Download file from internet.")
        ini_path = download(ini_path)
    if model_yaml_path.startswith("http"):
        logger.warning("Download file from internet.")
        model_yaml_path = download(model_yaml_path)

    rules, rule_providers, proxy_groups = parse_ini(ini_path)
    parse_yaml(rules, rule_providers, proxy_groups, model_yaml_path, output_path)

    logger.success(f"Convert success, output file: {os.path.abspath(output_path)}")
