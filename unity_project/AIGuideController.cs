public class AIGuideController : MonoBehaviour
{
    // Add these fields
    private string currentQueryId;
    
    void OnAskButtonClicked()
    {
        string question = questionInputField.text.Trim();
        
        if (string.IsNullOrEmpty(question))
        {
            responsePanel.SetActive(true);
            responseText.text = "Please type a question first!";
            return;
        }
        
        // Start analytics tracking
        AnalyticsManager.Instance.StartQuery(question);
        
        // Show loading
        responsePanel.SetActive(true);
        responseText.text = "Thinking...";
        
        // Send to API with metadata
        APIManager.Instance.AskQuestion(question, (response) => 
        {
            responseText.text = response.response;
            currentQueryId = response.query_id;
            
            // Record response in analytics
            List<AnalyticsManager.ArtworkData> artworkData = new List<AnalyticsManager.ArtworkData>();
            foreach (var art in response.artworks)
            {
                artworkData.Add(new AnalyticsManager.ArtworkData
                {
                    id = art.id.ToString(),
                    title = art.title,
                    artist = art.artist,
                    similarity = art.similarity
                });
            }
            
            AnalyticsManager.Instance.RecordQueryResponse(
                response.query_id,
                response.response,
                artworkData
            );
            
            // Highlight artworks
            HighlightArtworks(response.artworks);
            
            // Show feedback buttons
            ShowFeedbackButtons(response.query_id);
        });
    }
    
    void HighlightArtworks(List<ArtworkData> artworks)
    {
        foreach (var artwork in artworks)
        {
            GameObject artObject = GameObject.Find(artwork.id.ToString());
            if (artObject != null)
            {
                // Ensure it has a click tracker
                ArtworkClickTracker tracker = artObject.GetComponent<ArtworkClickTracker>();
                if (tracker == null)
                {
                    tracker = artObject.AddComponent<ArtworkClickTracker>();
                }
                
                tracker.artworkId = artwork.id.ToString();
                tracker.artworkTitle = artwork.title;
                tracker.artist = artwork.artist;
                
                // Visual highlight
                StartCoroutine(HighlightCoroutine(artObject));
            }
        }
    }
    
    IEnumerator HighlightCoroutine(GameObject artObject)
    {
        Renderer renderer = artObject.GetComponent<Renderer>();
        if (renderer != null)
        {
            Color original = renderer.material.color;
            renderer.material.color = Color.yellow;
            yield return new WaitForSeconds(3f);
            renderer.material.color = original;
        }
    }
    
    void ShowFeedbackButtons(string queryId)
    {
        // Create UI for feedback (thumbs up/down or 1-5 stars)
        // When clicked: AnalyticsManager.Instance.SubmitFeedback(score, "optional comment");
    }
    
    public void AskAboutArtwork(string artworkName)
    {
        // Use this when clicking on artworks
        questionInputField.text = $"Tell me about {artworkName}";
        OnAskButtonClicked();
    }
}
