# Eye Blink-Based Password Authentication

**Eye Blink-Based Password Authentication** is an innovative system designed to replace traditional password input methods with a more secure and accessible approach. This system enables users to input passwords by blinking their eyes in sync with a virtual keyboard where keys are highlighted sequentially. Additionally, the system incorporates **face recognition** to ensure only authorized users can access the system. Designed for applications such as ATMs, it not only enhances security but also serves as an assistive technology for individuals with disabilities.

---

## Project Overview

This project addresses the need for innovative, hands-free password authentication by providing:
- **Blink-Based Input**: A virtual keyboard where users blink at highlighted keys to input their passwords.
- **Face Recognition**: Additional security through user verification using facial recognition.
- **Enhanced ATM Security**: Prevents vulnerabilities like thermal detection attacks on physical keyboards.
- **Accessibility**: Offers an inclusive solution for individuals with disabilities, enabling them to authenticate without traditional input devices.

---

## Key Features

1. **Blink-Based Password Input**:
   - Users can enter passwords by blinking their eyes to select characters on a virtual keyboard.
   - Eliminates the physical keyboard, improving security and accessibility.

2. **Face Recognition for Authentication**:
   - Verifies the identity of the user before allowing access.
   - Adds an extra layer of security by ensuring only authorized users can proceed.

3. **Advanced Security Benefits**:
   - Prevents ATM risks such as thermal detection used to recover previous users’ passwords.
   - Reduces the attack surface by replacing physical input methods.

4. **Inclusive Design**:
   - Designed to assist people with disabilities by offering a hands-free password entry system.

---

## Technologies Used

- **Programming Language**: Python
- **Blink Detection**:
  - OpenCV for image processing and blink detection.
  - HOG (Histogram of Oriented Gradients) for feature extraction and blink recognition.
- **Face Recognition**:
  - Python’s face detection libraries to authenticate users.
- **User Interface**:
  - Implementation of a virtual keyboard with sequentially highlighted keys.

---

## How It Works

1. **Face Recognition**:
   - The system first performs facial recognition to authenticate the user visually.
   - Ensures the user’s identity matches the authorized individual.

2. **Blink-Based Password Input**:
   - A virtual keyboard is displayed, with keys lighting up sequentially.
   - The user blinks to select the character currently highlighted.
   - The process continues until the entire password is entered.

3. **Security and Accessibility**:
   - No physical keyboard is involved, mitigating risks such as thermal detection attacks.
   - Provides a more accessible method for password authentication to assist disabled users.

---

## Applications

- **ATM Authentication**:
  - Enhances security against common ATM threats, such as thermal tracking of keypresses.
- **Assistive Technology**:
  - Offers password input for people with motor impairments or disabilities.
- **Secure Systems**:
  - Can be extended to other secure systems requiring hands-free password entry.

---

## Future Scope

- **Improved Eye Tracking**:
  - Incorporate advanced techniques like infrared-based eye tracking for more precise input detection.
- **Enhanced Face Recognition**:
  - Integrate state-of-the-art AI models for faster and more secure face authentication.
- **Real-World ATM Integration**:
  - Expand the system to function seamlessly with real-world ATM setups.
- **Multi-Factor Authentication**:
  - Combine with other biometrics, such as fingerprint or voice recognition, for additional security.

---

## Contributors

- **Harshith Deshalli Ravi**  
  [GitHub](https://github.com/HarshithDR)

---

## Contact

For inquiries, suggestions, or collaboration opportunities, feel free to reach out to [Harshith Deshalli Ravi](https://github.com/HarshithDR).
