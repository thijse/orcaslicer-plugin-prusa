"""Prusa Connect GraphQL queries (connect-api.prusa3d.com), as used by the Connect web app."""

from __future__ import annotations

GRAPHQL_URL = "https://connect-api.prusa3d.com/graphql"

# Same selection as the web app's GetPrinterFffTelemetry; material name/colour per tool live only here.
PRINTER_FFF_TELEMETRY = """
query GetPrinterFffTelemetry($organizationId: UUID!, $printerId: UUID!) {
  printer {
    printer(organizationId: $organizationId, printerId: $printerId) {
      __typename
      ... on Printer {
        id
        printerType
        fff {
          hasMmuEnabled
          tools {
            id
            features { nozzleDiameter nozzleHighFlow nozzleHardened nozzleHighTemp }
            feeder { type model numSlots enabled }
            telemetry { active temp targetTemp }
            materialPackageInstance {
              __typename
              ... on FFFToolMaterialPackageInstance {
                uuid
                isFromNfc
                dynamicData { consumedWeight }
                package {
                  nominalNettoFullWeight
                  filamentDiameter
                  material {
                    uuid
                    name
                    abbreviation
                    brand { name }
                    primaryColor { colorRgba }
                    type { abbreviation }
                    properties {
                      minPrintTemperature
                      maxPrintTemperature
                      minBedTemperature
                      maxBedTemperature
                    }
                  }
                }
              }
              ... on ToolMaterialPackageInstanceEmpty { reason }
            }
          }
        }
      }
      ... on ConnectError { message }
    }
  }
}
"""

# The web app's material picker (Tools > Assign); search matches brand, name and type.
WAREHOUSE_MATERIALS = """
query WarehouseMaterials($organizationId: String!, $first: Int, $materialType: [String!], $search: String) {
  warehouse {
    materials(organizationId: $organizationId, first: $first, materialType: $materialType, search: $search) {
      nodes {
        uuid
        isCustom
        material { uuid name type abbreviation primaryColor { colorRgba } brand { name } }
      }
    }
  }
}
"""

# The material catalogue, with the print properties Connect has (about half the entries).
CATALOG_MATERIALS = """
query CatalogMaterials($organizationId: String!, $first: Int, $after: String, $search: String) {
  warehouse {
    materials(organizationId: $organizationId, first: $first, after: $after, search: $search, materialClass: [FFF]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        material {
          uuid name type class abbreviation tags url
          brand { name }
          primaryColor { colorRgba }
          properties { density chamberTemperature minPrintTemperature maxPrintTemperature minBedTemperature maxBedTemperature }
        }
      }
    }
  }
}
"""

# Records a material on a tool, like Tools > Assign; it does not load or move filament.
UPDATE_PRINTER_MATERIAL = """
mutation UpdatePrinterMaterial($organizationId: UUID!, $printerId: UUID!, $printer: PrinterUpdateInput!) {
  printer {
    updatePrinter(organizationId: $organizationId, printerId: $printerId, printer: $printer) {
      __typename
      ... on Printer { id }
      ... on ConnectError { message }
    }
  }
}
"""

# The camera service keeps the latest snapshot (every 30 s while printing) behind the same bearer token.
CAMERAS_BY_PRINTER = """
query CamerasByPrinter($printerUuid: UUID!, $first: Int! = 20) {
  camera {
    camerasConnection(printerUuid: $printerUuid, first: $first) {
      __typename
      ... on CameraConnection { edges { node { id name snapshots { lastSnapshotUrl } } } }
      ... on CameraServiceError { message }
    }
  }
}
"""
