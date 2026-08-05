import { getProductBySku, type ProductSku } from "../lib/catalog";

type Props = {
  sku: ProductSku;
};

export default function CheckoutSummary({ sku }: Props) {
  const product = getProductBySku(sku);
  return (
    <div className="terminal-card">
      <pre>{`SKU: ${product.sku}\nProduct: ${product.name}\nServer-side price: ${product.priceCents ? `$${(product.priceCents / 100).toFixed(2)}` : "Sales Contact"}\nLicense: ${product.licenseType ?? "Custom agreement"}`}</pre>
    </div>
  );
}
