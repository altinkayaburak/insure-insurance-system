import xml.etree.ElementTree as ET

def extract_paths_from_xml(xml_str, max_depth=5, prefix=''):
    def _recurse(element, path=''):
        if len(path.split('.')) > max_depth:
            return
        children = list(element)
        tag = element.tag.split('}')[-1]  # Namespace kaldır
        new_path = f"{path}.{tag}" if path else tag

        if not children:
            paths.add(new_path)
        else:
            for child in children:
                _recurse(child, new_path)

    paths = set()
    root = ET.fromstring(xml_str)
    _recurse(root)
    return sorted(paths)

# Kullanım:
xml = """
<SİGORTALILAR>

    <SİGORTALI>

        <MüşteriNumarası>2220072</MüşteriNumarası>

        <AdıSoyadı-Ünvanı>ÖMER KÜTÜKCÜ</AdıSoyadı-Ünvanı>

        <Ad>ÖMER</Ad>

        <SoyAd>KÜTÜKCÜ</SoyAd>

        <DoğumTarihi>19950509</DoğumTarihi>

        <EvTelefonu1></EvTelefonu1>

        <EvTelefonu2>905394080590</EvTelefonu2><İşTelefonu1>

    </İşTelefonu1><İşTelefonu2>

</İşTelefonu2>

<FaxNumarası></FaxNumarası>

<CepNumarası>905394080590</CepNumarası>

<E-Posta></E-Posta>

<VergiKimlikNumarası></VergiKimlikNumarası>

<VergiDairesi></VergiDairesi>

<TCKimlikNumarası>47068103526</TCKimlikNumarası>

<pasaportNo></pasaportNo><ÖzelTüzelKodu>Ö

</ÖzelTüzelKodu>

<Uyruğu>T.C.</Uyruğu>

<BabaAdı>ARİF</BabaAdı>

<Adres1>BALCANA KÖYÜ MERKEZ MEVKİİ MERKEZ KÜME EVLERİ  NO: 16  İÇ KAPI NO: 1 ŞEBİNKARAHİSAR / GİRESUN</Adres1>

<Adres2></Adres2>

<Adres3></Adres3>

<Adres4></Adres4>

<Adres5></Adres5><İlçeKodu>1654

</İlçeKodu><İlçe>ŞEBİNKARAHİSAR

</İlçe><İlKodu>28

</İlKodu><İl>GİRESUN

</İl>

<IlceKodBelde>14759</IlceKodBelde>

<TemsilciNo>0</TemsilciNo>

<PostaKod>0</PostaKod>

</SİGORTALI>

</SİGORTALILAR>"""
for p in extract_paths_from_xml(xml):
    print(p)

