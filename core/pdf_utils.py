import os
import fitz  # PyMuPDF

def render_pdf_to_images(pdf_path: str, output_dir: str) -> list[str]:
    """
    Renders each page of the PDF at pdf_path to a separate PNG file in output_dir.
    Returns a list of file paths to the generated PNGs.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    doc = fitz.open(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    image_paths = []
    
    for i in range(len(doc)):
        page = doc[i]
        # 150 DPI is a good balance between quality and size for VLM
        pix = page.get_pixmap(dpi=150)
        
        # 1-indexed page number
        out_path = os.path.join(output_dir, f"{base_name}_page_{i+1}.png")
        pix.save(out_path)
        image_paths.append(out_path)
        
    doc.close()
    return image_paths
