import { firebaseConfig, firebaseSdkVersion } from "/firebase-config.js";

const firebaseBase = `https://www.gstatic.com/firebasejs/${firebaseSdkVersion}`;
const { initializeApp } = await import(`${firebaseBase}/firebase-app.js`);
const {
  collection,
  doc,
  getDocs,
  getFirestore,
  query,
  serverTimestamp,
  setDoc,
  where
} = await import(`${firebaseBase}/firebase-firestore.js`);

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const section = document.querySelector(".recipe-reviews[data-recipe-id]");

if (section) {
  const recipeId = section.dataset.recipeId;
  const recipeTitle = section.dataset.recipeTitle;
  const recipeUrl = section.dataset.recipeUrl;
  const summaryAverage = section.querySelector("[data-reviews-average]");
  const summaryStars = section.querySelector("[data-reviews-stars]");
  const summaryCount = section.querySelector("[data-reviews-count]");
  const reviewList = section.querySelector("[data-reviews-list]");
  const form = section.querySelector("[data-review-form]");
  const formStatus = section.querySelector("[data-review-status]");

  const escapeStars = (rating) => `${"★".repeat(rating)}${"☆".repeat(5 - rating)}`;
  const plural = (count) => count === 1 ? "1 reseña" : `${count} reseñas`;

  function timestampMillis(value) {
    return value && typeof value.toMillis === "function" ? value.toMillis() : 0;
  }

  function reviewDate(value) {
    if (!value || typeof value.toDate !== "function") return "";
    return new Intl.DateTimeFormat("es-ES", {
      day: "numeric",
      month: "long",
      year: "numeric"
    }).format(value.toDate());
  }

  function renderReviews(reviews) {
    reviewList.replaceChildren();
    if (!reviews.length) {
      summaryAverage.textContent = "—";
      summaryStars.textContent = "☆☆☆☆☆";
      summaryCount.textContent = "Todavía no hay reseñas publicadas";
      const empty = document.createElement("p");
      empty.className = "recipe-reviews__empty";
      empty.textContent = "Sé la primera persona en contar cómo te ha quedado.";
      reviewList.append(empty);
      return;
    }

    const average = reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length;
    summaryAverage.textContent = average.toLocaleString("es-ES", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    });
    summaryStars.textContent = escapeStars(Math.round(average));
    summaryCount.textContent = `${average.toLocaleString("es-ES", { maximumFractionDigits: 1 })} de 5 · ${plural(reviews.length)}`;

    reviews
      .slice()
      .sort((a, b) => timestampMillis(b.createdAt) - timestampMillis(a.createdAt))
      .forEach((review) => {
        const article = document.createElement("article");
        article.className = "recipe-review";

        const heading = document.createElement("div");
        heading.className = "recipe-review__heading";

        const author = document.createElement("strong");
        author.textContent = review.name;

        const stars = document.createElement("span");
        stars.className = "recipe-review__stars";
        stars.setAttribute("aria-label", `${review.rating} de 5 estrellas`);
        stars.textContent = escapeStars(review.rating);

        const comment = document.createElement("p");
        comment.textContent = review.comment;

        heading.append(author, stars);
        article.append(heading, comment);

        const date = reviewDate(review.createdAt);
        if (date) {
          const time = document.createElement("time");
          time.className = "recipe-review__date";
          time.textContent = date;
          article.append(time);
        }
        reviewList.append(article);
      });

    addReviewsToRecipeSchema(reviews, average);
  }

  function addReviewsToRecipeSchema(reviews, average) {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      let payload;
      try {
        payload = JSON.parse(script.textContent);
      } catch {
        continue;
      }

      const candidates = payload && Array.isArray(payload["@graph"])
        ? payload["@graph"]
        : [payload];
      const recipe = candidates.find((item) => {
        const type = item && item["@type"];
        return type === "Recipe" || (Array.isArray(type) && type.includes("Recipe"));
      });
      if (!recipe) continue;

      recipe.aggregateRating = {
        "@type": "AggregateRating",
        ratingValue: Number(average.toFixed(2)),
        reviewCount: reviews.length,
        bestRating: 5,
        worstRating: 1
      };
      recipe.review = reviews.map((review) => {
        const structuredReview = {
          "@type": "Review",
          author: { "@type": "Person", name: review.name },
          reviewBody: review.comment,
          reviewRating: {
            "@type": "Rating",
            ratingValue: review.rating,
            bestRating: 5,
            worstRating: 1
          }
        };
        if (review.createdAt && typeof review.createdAt.toDate === "function") {
          structuredReview.datePublished = review.createdAt.toDate().toISOString().slice(0, 10);
        }
        return structuredReview;
      });
      script.textContent = JSON.stringify(payload);
      break;
    }
  }

  async function loadApprovedReviews() {
    try {
      const approved = query(
        collection(db, "reviews"),
        where("recipeId", "==", recipeId),
        where("status", "==", "approved")
      );
      const snapshot = await getDocs(approved);
      renderReviews(snapshot.docs.map((item) => item.data()));
    } catch (error) {
      console.error("No se pudieron cargar las reseñas", error);
      summaryAverage.textContent = "—";
      summaryStars.textContent = "☆☆☆☆☆";
      summaryCount.textContent = "No se pudieron cargar las reseñas";
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const fields = new FormData(form);
    if (String(fields.get("website") || "").trim()) {
      form.reset();
      formStatus.textContent = "Gracias. Tu reseña se ha recibido.";
      return;
    }

    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    formStatus.textContent = "Enviando…";

    try {
      const { getAuth, signInAnonymously } = await import(`${firebaseBase}/firebase-auth.js`);
      const credential = await signInAnonymously(getAuth(app));
      const reviewId = `${recipeId}--${credential.user.uid}`;
      await setDoc(doc(db, "reviews", reviewId), {
        recipeId,
        recipeTitle,
        recipeUrl,
        name: String(fields.get("name")).trim(),
        rating: Number(fields.get("rating")),
        comment: String(fields.get("comment")).trim(),
        status: "pending",
        createdAt: serverTimestamp()
      });
      form.reset();
      formStatus.textContent = "¡Gracias! Tu reseña se publicará en cuanto Sandra la apruebe.";
    } catch (error) {
      console.error("No se pudo enviar la reseña", error);
      formStatus.textContent = error && error.code === "permission-denied"
        ? "Ya has enviado una reseña para esta receta o no ha sido posible validarla."
        : "No se ha podido enviar ahora. Inténtalo de nuevo dentro de unos minutos.";
    } finally {
      button.disabled = false;
    }
  });

  loadApprovedReviews();
}
