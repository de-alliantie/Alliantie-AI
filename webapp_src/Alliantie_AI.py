import streamlit as st
from helpers_webapp import set_styling

set_styling()

st.markdown("# Alliantie AI")
st.markdown(
    "Ga eenvoudig én veilig aan de slag met generatieve AI-toepassingen. Alliantie AI maakt je werk nog leuker, sneller en slimmer."  # noqa: E501
)
st.markdown("######")  # insert whitespace
st.markdown(
    """
    ##### Momenteel bestaat Alliantie AI uit twee tools:
    """
)

# --- Buttons to subpages ---
col1, col2, col3 = st.columns([1, 0.2, 1])  # Make col2 smaller for whitespace
with col1:
    if st.button("💬 **Veilig ChatGPT**", use_container_width=True):
        st.switch_page("pages/1_💬_Veilig_ChatGPT.py")
with col2:
    st.write("")  # Add whitespace
with col3:
    if st.button("🖋️ **Notulen Generator**", use_container_width=True):
        st.switch_page("pages/2_🖋️_Notulen_Generator.py")

col3, col4, col5 = st.columns([1, 0.2, 1])
with col3:
    st.markdown(
        """
        ##### Veilig en privacyvriendelijk ChatGPT gebruiken
        - Upload je eigen bestanden (zoals Word, PDF, Excel, afbeeldingen)
        - Of plak emails, teksten of andere documenten in de chat
        - Stel er vragen over of geef bewerkingsopdrachten
        - Denk aan:
            - Eén samenvatting of vergelijking van 5 aparte PDF-bestanden
            - Een conceptmail op basis van bijlagen
            - Een berekening, formule of grafiek op basis van je Excel-data
        """
    )
with col4:
    st.write("")  # Add whitespace
with col5:
    st.markdown(
        """
        ##### Genereer notulen van je vergadering
        - Lever een agenda en geluidsopname aan
        - De tool stelt concept-notulen voor je op
        - Inclusief actiepunten en besluiten
    """
    )

st.markdown("######")  # insert whitespace

# --- Handige tips section ---
st.markdown("##### Ga naar [🔒 Informatie en Privacy](Informatie_en_Privacy) voor handige info en tips:")
st.markdown("❓ Wat is generatieve AI?")
st.markdown("💡 Hoe maak je een goede prompt?")
st.markdown("⚠️ Gebruik geen bijzondere persoonsgegevens")
